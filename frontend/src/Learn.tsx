import { useState, useEffect, useRef } from 'react';
import { ArrowRight, ArrowUpRight, CheckCircle2, Upload } from 'lucide-react';
import { download, json, privateMedia } from './api';
import { pollJob as poll } from './lib/analysis';
import type { AnalysisJob } from './lib/workspace';
import type { Health, Protocol, Run, Validation } from './types';
import './styles/teach.css';
import { ErrorNotice } from './components/ErrorNotice';
import { AnalysisProgress, type JobProgress } from './components/AnalysisProgress';

const checks: [string, string, string][] = [
  [
    'discriminative',
    'Each step is clear',
    'A step needs a visible change before it can be checked.',
  ],
  ['compile_replay', 'Works on your first video', 'The teaching video must follow every step.'],
  ['held_out', 'Works on a second video', 'Another take must follow the same steps.'],
  ['counterfactual', 'Catches mistakes', 'Missing or reordered steps must be flagged.'],
];
type Range = { start: number | null; end: number | null };
type ProtocolStatus = {
  progress?: JobProgress;
  status: string;
  error?: string;
  protocol?: Protocol;
  validation?: Validation | null;
  boundary_suggestions?: Record<string, Range>;
  confirmed_ranges?: Record<string, Range>;
};
export type TeachingProcedure = { id: string; protocol: Protocol };
export function Learn({
  run,
  health,
  source,
  initialJob,
  readOnly = false,
  onSignIn,
  onProtocolReady,
  onNavigateCheck,
}: {
  readOnly?: boolean;
  onSignIn?: () => void;
  run: Run;
  health: Health;
  onRun: (run: Run) => void;
  source?: { file: File; kind: 'expert' | 'held_out' | 'novice' } | null;
  initialJob?: AnalysisJob | null;
  onProtocolReady?: (procedure: TeachingProcedure) => void;
  onNavigateCheck?: () => void;
}) {
  const [stage, setStage] = useState<1 | 2 | 3>(1);
  const [teaching, setTeaching] = useState<File | null>(null);
  const [second, setSecond] = useState<File | null>(null);
  const [description, setDescription] = useState('');
  const [protocol, setProtocol] = useState<Protocol>(run.protocol);
  const [validation, setValidation] = useState<Validation | undefined>();
  const [id, setId] = useState('');
  const [example, setExample] = useState(false);
  const [videoUrl, setVideoUrl] = useState('');
  const [videoError, setVideoError] = useState('');
  const [duration, setDuration] = useState(0);
  const [ranges, setRanges] = useState<Record<string, Range>>({});
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState('');
  const [progress, setProgress] = useState<JobProgress>();
  const [error, setError] = useState<unknown>(null);
  const [repair, setRepair] = useState(false);
  const player = useRef<HTMLVideoElement>(null);
  const taskGeneration = useRef(0);

  useEffect(
    () => () => {
      taskGeneration.current += 1;
    },
    [],
  );

  useEffect(() => {
    if (source?.kind === 'expert') {
      invalidateTeaching();
      setTeaching(source.file);
    } else if (source?.kind === 'held_out') {
      replaceSecond(source.file);
      setStage(2);
    }
  }, [source]);
  useEffect(() => {
    if (!initialJob?.result.protocol) return;
    const result = initialJob.result as ProtocolStatus;
    const loaded = result.protocol!;
    invalidateTask();
    setTeaching(null);
    setDescription('');
    setSecond(null);
    setId(initialJob.id);
    setProtocol(loaded);
    setExample(false);
    setValidation(result.validation ?? undefined);
    setRanges(result.confirmed_ranges ?? result.boundary_suggestions ?? {});
    setConfirmed(false);
    setStage(2);
    onProtocolReady?.({ id: initialJob.id, protocol: loaded });
  }, [initialJob]);
  useEffect(() => {
    let disposed = false;
    let url = '';
    setVideoUrl('');
    setVideoError('');
    setDuration(0);
    if (teaching) {
      url = URL.createObjectURL(teaching);
      setVideoUrl(url);
    } else if (id && !example) {
      void privateMedia(`/api/media/${id}/original.mp4`)
        .then((value) => {
          url = value;
          if (disposed) URL.revokeObjectURL(value);
          else setVideoUrl(value);
        })
        .catch(() => {
          if (!disposed)
            setVideoError(
              'Teaching video unavailable. Add the original video to review its timings.',
            );
        });
    }
    return () => {
      disposed = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [teaching, id, example]);
  useEffect(() => {
    if (!duration || example || !id) return;
    setRanges((current) =>
      Object.fromEntries(
        protocol.steps.map((step, index) => [
          step.id,
          current[step.id]?.start !== null && current[step.id]?.end !== null && current[step.id]
            ? current[step.id]
            : {
                start: (duration * index) / protocol.steps.length,
                end:
                  index === protocol.steps.length - 1
                    ? duration
                    : (duration * (index + 1)) / protocol.steps.length,
              },
        ]),
      ),
    );
    setConfirmed(false);
  }, [duration, protocol, example, id]);

  const live = health.live_configured && !health.replay_mode && !readOnly;
  const createReason = busy
    ? 'Wait for the current task to finish.'
    : readOnly
      ? 'Sign in to upload your own teaching video.'
      : !health.live_configured || health.replay_mode
        ? "Analysis isn't connected here — try the sample."
        : !teaching
          ? 'Add a video to continue.'
          : '';
  const invalidStep = protocol.steps.find((step) => {
    const range = ranges[step.id];
    return (
      !range ||
      range.start === null ||
      range.end === null ||
      !Number.isFinite(range.start) ||
      !Number.isFinite(range.end) ||
      range.start < 0 ||
      range.start >= range.end ||
      range.end > duration
    );
  });
  const placeholders =
    protocol.steps.length > 0 &&
    protocol.steps.every((step) => ranges[step.id]?.start === 0 && ranges[step.id]?.end === 1);
  const checkReason = busy
    ? 'Wait for the current task to finish.'
    : example
      ? 'Example steps are read-only. Use your own teaching video to run these checks.'
      : !live
        ? "Analysis isn't connected here — try the sample."
        : !id
          ? 'Create the steps first.'
          : !second
            ? 'Add a second video of the same procedure.'
            : !duration
              ? 'Load the teaching video to check its duration.'
              : invalidStep
                ? `Adjust the start and end for “${invalidStep.title}”.`
                : placeholders
                  ? 'Adjust the suggested timings to match the video.'
                  : !confirmed
                    ? 'Review every timing, then confirm below.'
                    : '';
  async function task(message: string, action: (generation: number) => Promise<void>) {
    if (readOnly) {
      onSignIn?.();
      return;
    }
    const generation = ++taskGeneration.current;
    setBusy(message);
    setProgress(undefined);
    setError(null);
    try {
      await action(generation);
    } catch (caught) {
      if (generation === taskGeneration.current) setError(caught);
    } finally {
      if (generation === taskGeneration.current) setBusy('');
    }
  }
  async function createSteps() {
    if (!teaching || createReason) return;
    await task('Reading the video and writing the steps…', async (generation) => {
      const form = new FormData();
      form.set('video', teaching);
      form.set('narration_text', description.trim());
      const created = await json<{ protocol_id: string }>('/api/protocols', {
        method: 'POST',
        body: form,
      });
      if (generation !== taskGeneration.current) return;
      const result = await poll<ProtocolStatus>(
        `/api/protocols/${created.protocol_id}`,
        (update) => {
          if (generation === taskGeneration.current) setProgress(update.progress);
        },
      );
      if (generation !== taskGeneration.current) return;
      if (!result.protocol)
        throw new Error('The steps were not returned. Please reopen this task.');
      setId(created.protocol_id);
      setProtocol(result.protocol);
      setValidation(undefined);
      setExample(false);
      setRanges(result.boundary_suggestions ?? {});
      setConfirmed(false);
      setStage(2);
      onProtocolReady?.({ id: created.protocol_id, protocol: result.protocol });
    });
  }
  async function checkSteps() {
    if (!second || checkReason) return;
    await task('Checking both videos and deliberate mistakes…', async (generation) => {
      const form = new FormData();
      form.set('heldout', second);
      form.set('ranges', JSON.stringify(ranges));
      form.set('ranges_confirmed', String(confirmed));
      form.set('repair', String(repair));
      await json(`/api/protocols/${id}/validate`, { method: 'POST', body: form });
      if (generation !== taskGeneration.current) return;
      const result = await poll<ProtocolStatus>(`/api/protocols/${id}`, (update) => {
        if (generation === taskGeneration.current) setProgress(update.progress);
      });
      if (generation !== taskGeneration.current) return;
      if (result.protocol) {
        setProtocol(result.protocol);
        onProtocolReady?.({ id, protocol: result.protocol });
      }
      setValidation(result.validation ?? undefined);
    });
  }
  function invalidateTask() {
    taskGeneration.current += 1;
    setBusy('');
    setError(null);
  }
  function replaceSecond(file: File | null) {
    invalidateTask();
    setSecond(file);
    setValidation(undefined);
  }
  function invalidateTeaching() {
    invalidateTask();
    setId('');
    setValidation(undefined);
    setRanges({});
    setConfirmed(false);
    setSecond(null);
    setExample(false);
    setProtocol(run.protocol);
    setStage(1);
    onProtocolReady?.({ id: '', protocol: run.protocol });
  }
  function chooseExample() {
    invalidateTask();
    setProtocol(run.protocol);
    setExample(true);
    setId('');
    setValidation(undefined);
    setRanges({});
    setConfirmed(false);
    setStage(2);
    onProtocolReady?.({ id: '', protocol: run.protocol });
  }
  function mark(stepId: string, edge: 'start' | 'end', value: number | null) {
    setRanges((current) => ({
      ...current,
      [stepId]: { ...(current[stepId] ?? { start: null, end: null }), [edge]: value },
    }));
    setConfirmed(false);
  }
  return (
    <div className={`teach-flow${busy ? ' is-processing' : ''}`}>
      <ol className="teach-progress" aria-label="Teaching progress">
        {['Show the right way', 'Check the steps', 'Try a new recording'].map((title, index) => (
          <li key={title} aria-current={stage === index + 1 ? 'step' : undefined}>
            <span>{index + 1}</span>
            {title}
          </li>
        ))}
      </ol>
      {busy && <AnalysisProgress message={busy} progress={progress} />}
      <section className="panel teach-stage" aria-label="Show the right way">
        <div className="section-heading">
          <h2>1 Show the right way</h2>
          {stage !== 1 && (
            <button className="text-button" onClick={() => setStage(1)} disabled={!!busy}>
              Edit
            </button>
          )}
        </div>
        {stage !== 1 ? (
          <p className="muted">
            {example
              ? 'Example steps selected — no video was analysed.'
              : (teaching?.name ?? 'Teaching video saved with this procedure.')}
          </p>
        ) : (
          <>
            <p>Upload a video showing the right way to do one hands-on procedure.</p>
            <FileInput
              label="Teaching video"
              file={teaching}
              onFile={(file) => {
                invalidateTeaching();
                setTeaching(file);
              }}
              disabled={readOnly || !!busy}
            />
            {readOnly && (
              <button className="text-button" onClick={onSignIn}>
                Sign in to upload a recording
              </button>
            )}
            <a
              className="text-button"
              href="https://www.youtube.com/watch?v=gmeCY7ANrog"
              target="_blank"
              rel="noopener noreferrer"
            >
              Need a sample video? <ArrowUpRight size={14} />
            </a>
            <p className="field-help">
              Science Buddies reference. Upload only recordings you have permission to analyse.
            </p>
            <label className="field-label" htmlFor="narration">
              Describe what happens (optional)
            </label>
            <textarea
              id="narration"
              rows={3}
              value={description}
              maxLength={4000}
              onChange={(event) => {
                invalidateTeaching();
                setDescription(event.target.value);
              }}
              disabled={readOnly || !!busy}
              placeholder="For example: place the dropper back, then put the cap on the blue tube."
            />
            <p className="field-help">
              If you provide a description, it is used as narration for the whole video. Without
              one, the app transcribes the audio. Timing suggestions always need your review.
            </p>
            <button
              className="button primary"
              disabled={!!createReason}
              aria-describedby="create-steps-reason"
              onClick={() => void createSteps()}
            >
              Create the steps <ArrowRight size={16} />
            </button>
            <p id="create-steps-reason" className="field-help">
              {createReason || 'Ready to create a checklist from your video.'}
            </p>
            <button className="button" onClick={chooseExample} disabled={!!busy}>
              Use the sample steps
            </button>
          </>
        )}
      </section>
      {(stage >= 2 || id || example) && (
        <section className="panel teach-stage learned-protocol" aria-label="Check the steps">
          <div className="section-heading">
            <h2>2 Check the steps</h2>
            {example && <span className="example-tag">Example</span>}
            {stage === 3 && (
              <button className="text-button" onClick={() => setStage(2)}>
                Edit
              </button>
            )}
          </div>
          {stage !== 2 ? (
            <p className="muted">
              {protocol.steps.length} steps reviewed.{' '}
              {validation?.verified
                ? 'All four checks passed.'
                : 'Checks do not yet establish a verified procedure.'}
            </p>
          ) : (
            <>
              <h3>{protocol.name}</h3>
              <p className="muted">
                {example
                  ? 'Animated example — these steps were written by hand, not learned from a video.'
                  : 'Review the suggested steps and their timing before running the checks.'}
              </p>
              <div className="protocol-cards">
                {protocol.steps.map((step, index) => (
                  <article key={step.id}>
                    <h3>
                      <span className="small-number">{index + 1}</span> {step.title}
                    </h3>
                    <p>{step.narration_hint || 'Review this step against the teaching video.'}</p>
                  </article>
                ))}
              </div>
              {!example && (
                <>
                  <h3>When does each step happen?</h3>
                  <p className="field-help">
                    Suggested — adjust. Narration gives a starting point; unmatched steps are spaced
                    evenly across the video. Watch the action and mark its start and end.
                  </p>
                  {videoUrl && (
                    <video
                      className="teaching-player"
                      ref={player}
                      src={videoUrl}
                      controls
                      preload="metadata"
                      aria-label="Teaching video timing editor"
                      onLoadedMetadata={(event) => {
                        const value = event.currentTarget.duration;
                        if (Number.isFinite(value) && value > 0 && value <= 90) setDuration(value);
                        else
                          setVideoError('Use a video with a valid duration of up to 90 seconds.');
                      }}
                    />
                  )}
                  {videoError && <p role="alert">{videoError}</p>}
                  {!videoUrl && (
                    <p className="field-help">Add the teaching video to review the timings.</p>
                  )}
                  <div className="step-timeline">
                    {protocol.steps.map((step) => (
                      <fieldset key={step.id}>
                        <legend>{step.title}</legend>
                        {(['start', 'end'] as const).map((edge) => (
                          <div className="timing-control" key={edge}>
                            <label>
                              {edge === 'start' ? 'Start' : 'End'} (seconds)
                              <input
                                type="number"
                                min={0}
                                max={duration || 90}
                                step="0.1"
                                value={ranges[step.id]?.[edge] ?? ''}
                                aria-label={`${step.title} ${edge} in seconds`}
                                onChange={(event) =>
                                  mark(
                                    step.id,
                                    edge,
                                    event.target.value === '' ? null : Number(event.target.value),
                                  )
                                }
                                disabled={!!busy}
                              />
                            </label>
                            <button
                              className="button"
                              disabled={!duration || !!busy}
                              aria-label={`${step.title}: mark ${edge} here`}
                              onClick={() => mark(step.id, edge, player.current?.currentTime ?? 0)}
                            >
                              Mark {edge} here
                            </button>
                          </div>
                        ))}
                      </fieldset>
                    ))}
                  </div>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      disabled={!!busy || !duration || !!invalidStep}
                      onChange={(event) => setConfirmed(event.target.checked)}
                    />
                    I checked every start and end against the teaching video
                  </label>
                  <FileInput
                    label="Second video (same procedure, different take)"
                    file={second}
                    onFile={replaceSecond}
                    disabled={!!busy}
                  />
                  <button
                    className="button primary"
                    disabled={!!checkReason}
                    aria-describedby="check-steps-reason"
                    onClick={() => void checkSteps()}
                  >
                    Run the checks
                  </button>
                  <p id="check-steps-reason" className="field-help">
                    {checkReason || 'Ready to check both videos and deliberate mistakes.'}
                  </p>
                </>
              )}
              {validation && (
                <div className="validation-checks" aria-label="Check results">
                  {checks.map(([key, title, reason]) => (
                    <div
                      key={key}
                      className={validation.checks[key] === true ? 'passed' : 'failed'}
                    >
                      <div>
                        <strong>{title}</strong>
                        <span>
                          {validation.checks[key] === true
                            ? 'Passed'
                            : validation.checks[key] === false
                              ? 'Needs attention'
                              : 'Not completed'}
                        </span>
                        {validation.checks[key] !== true && (
                          <>
                            <p>{reason}</p>
                            <details>
                              <summary>Show details</summary>
                              <p>{validation.scope}</p>
                            </details>
                          </>
                        )}
                      </div>
                      {validation.checks[key] === true && <CheckCircle2 size={18} />}
                    </div>
                  ))}
                </div>
              )}
              <details className="teach-advanced">
                <summary>Advanced details</summary>
                <p className="mono">Protocol ID: {id || 'Example only'}</p>
                <p>
                  Verified: {protocol.verified ? 'yes' : 'no'} · repair rounds:{' '}
                  {validation?.repair_rounds ?? 0}
                </p>
                <button
                  className="button"
                  onClick={() => download('protocol.json', JSON.stringify(protocol, null, 2))}
                >
                  Export JSON
                </button>
                {!example && (
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={repair}
                      onChange={(event) => setRepair(event.target.checked)}
                      disabled={!!busy}
                    />
                    Allow up to 3 model repair rounds within budget
                  </label>
                )}
                {protocol.steps.map((step) => (
                  <article key={step.id}>
                    <h4>{step.title}</h4>
                    <p className="mono">Step ID: {step.id}</p>
                    <p>
                      Dwell {step.min_dwell_s}–{step.max_dwell_s}s ·{' '}
                      {step.group ? `unordered group ${step.group}` : 'ordered step'}
                    </p>
                    <p>Completion rule (JSON)</p>
                    <pre>{JSON.stringify(step.post, null, 2)}</pre>
                  </article>
                ))}
              </details>
              <p className="field-help">
                Visible contact cannot prove liquid volume, concentration, sterility or cap
                tightness.
              </p>
              <button className="button" disabled={!!busy} onClick={() => setStage(3)}>
                Continue to a new recording <ArrowRight size={16} />
              </button>
            </>
          )}
        </section>
      )}
      {stage === 3 && (
        <section className="panel teach-stage">
          <h2>3 Try a new recording</h2>
          <p>
            {example
              ? 'The example checklist is read-only. Open Check to explore an animated result or teach your own procedure.'
              : validation?.verified
                ? 'All four checks passed. Open Check to upload another recording of this procedure.'
                : 'You can try another recording, but these steps are not yet verified. Open Check to continue.'}
          </p>
          <button
            className="button primary"
            onClick={onNavigateCheck}
            disabled={!onNavigateCheck}
            aria-describedby="open-check-reason"
          >
            Go to Check <ArrowRight size={16} />
          </button>
          <p id="open-check-reason" className="field-help">
            {onNavigateCheck
              ? 'Choose your next recording on the Check page.'
              : 'Open Check from the sidebar to continue.'}
          </p>
        </section>
      )}
      <ErrorNotice error={error} />
    </div>
  );
}
function FileInput({
  label,
  file,
  onFile,
  disabled = false,
}: {
  label: string;
  file: File | null;
  onFile: (file: File | null) => void;
  disabled?: boolean;
}) {
  return (
    <label className="file-input">
      <Upload size={20} />
      <span>
        <strong>{label}</strong>
        <small>{file ? file.name : 'Choose MP4 / MOV · up to 90 seconds'}</small>
      </span>
      <input
        type="file"
        aria-label={label}
        accept="video/mp4,video/quicktime"
        disabled={disabled}
        onChange={(event) => onFile(event.target.files?.[0] ?? null)}
      />
    </label>
  );
}
