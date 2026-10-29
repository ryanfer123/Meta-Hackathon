import { useState, useEffect } from 'react';
import { ArrowUpRight, CheckCircle2, Clock3, FileVideo, Upload } from 'lucide-react';
import { download, json } from './api';
import type { AnalysisJob } from './lib/workspace';
import type { Health, Protocol, Run, Validation } from './types';
const checks: [string, string, string][] = [
  ['discriminative', 'Visible change', 'Each step has a visible change'],
  ['compile_replay', 'Original example', 'The original example passes'],
  ['held_out', 'Second example', 'A second example also passes'],
  ['counterfactual', 'Deliberate mistakes', 'Missing or reordered steps are flagged'],
];
type ProtocolStatus = {
  status: string;
  error?: string;
  protocol?: Protocol;
  validation?: Validation | null;
  boundary_suggestions?: Record<string, { start: number; end: number }>;
  confirmed_ranges?: Record<string, { start: number; end: number }>;
};
async function poll<T extends { status?: string; error?: string }>(path: string): Promise<T> {
  for (let n = 0; n < 300; n++) {
    const result = await json<T>(path);
    if (result.status === 'error') throw new Error(result.error ?? 'Processing failed');
    if (result.status === 'ready') return result;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error('Processing continues on the server. Check its status before retrying.');
}
export function Learn({
  run,
  health,
  onRun,
  source,
  initialJob,
  readOnly = false,
  onSignIn,
}: {
  readOnly?: boolean;
  onSignIn?: () => void;
  run: Run;
  health: Health;
  onRun: (run: Run) => void;
  source?: { file: File; kind: 'expert' | 'held_out' | 'novice' } | null;
  initialJob?: AnalysisJob | null;
}) {
  const [expert, setExpert] = useState<File | null>(null),
    [heldout, setHeldout] = useState<File | null>(null),
    [novice, setNovice] = useState<File | null>(null),
    [narration, setNarration] = useState('[]'),
    [ranges, setRanges] = useState('{}'),
    [rangesConfirmed, setRangesConfirmed] = useState(false),
    [boundaryNote, setBoundaryNote] = useState('');
  const [protocol, setProtocol] = useState<Protocol>(run.protocol),
    [validation, setValidation] = useState<Validation | undefined>(run.validation),
    [id, setId] = useState(''),
    [busy, setBusy] = useState(''),
    [error, setError] = useState(''),
    [repair, setRepair] = useState(false);
  useEffect(() => {
    if (source) {
      if (source.kind === 'expert') setExpert(source.file);
      else if (source.kind === 'held_out') setHeldout(source.file);
      else setNovice(source.file);
    }
  }, [source]);
  useEffect(() => {
    if (initialJob?.result.protocol) {
      setId(initialJob.id);
      setProtocol(initialJob.result.protocol as Protocol);
      setValidation(initialJob.result.validation as Validation | undefined);
      applyBoundarySuggestions(initialJob.result as ProtocolStatus);
    }
  }, [initialJob]);
  function applyBoundarySuggestions(result: ProtocolStatus) {
    if (!result.protocol) return;
    const suggestions = result.confirmed_ranges ?? result.boundary_suggestions ?? {};
    const missing = result.protocol.steps.filter((step) => !suggestions[step.id]);
    setRanges(
      JSON.stringify(
        Object.fromEntries(
          result.protocol.steps.map((step) => [
            step.id,
            suggestions[step.id] ?? { start: null, end: null },
          ]),
        ),
        null,
        2,
      ),
    );
    setRangesConfirmed(false);
    setBoundaryNote(
      (result.confirmed_ranges
        ? 'Previously reviewed timings loaded. Review again before rerunning validation. '
        : `${Object.keys(suggestions).length} timing proposals from narration. `) +
        (missing.length
          ? `Fill missing times for: ${missing.map((step) => step.title).join(', ')}. `
          : '') +
        'Narration may lead or lag the action. Check that each start is before the action and each end is after it.',
    );
  }
  const live = health.live_configured;
  async function task(name: string, fn: () => Promise<void>) {
    if (readOnly) {
      onSignIn?.();
      return;
    }
    setBusy(name);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setBusy('');
    }
  }
  async function compile() {
    if (!expert) return;
    await task('Compiling expert recording…', async () => {
      const f = new FormData();
      f.set('video', expert);
      f.set('narration', narration);
      const result = await json<{ protocol_id: string }>('/api/protocols', {
        method: 'POST',
        body: f,
      });
      setId(result.protocol_id);
      const done = await poll<ProtocolStatus>(`/api/protocols/${result.protocol_id}`);
      if (done.protocol) {
        setProtocol(done.protocol);
        setValidation(undefined);
        applyBoundarySuggestions(done);
      }
    });
  }
  async function validate() {
    if (!heldout || !id) return;
    await task('Checking expert A/B and counterfactuals…', async () => {
      const f = new FormData();
      f.set('heldout', heldout);
      f.set('ranges', ranges);
      f.set('ranges_confirmed', String(rangesConfirmed));
      f.set('repair', String(repair));
      await json(`/api/protocols/${id}/validate`, { method: 'POST', body: f });
      const done = await poll<ProtocolStatus>(`/api/protocols/${id}`);
      if (done.protocol) setProtocol(done.protocol);
      setValidation(done.validation ?? undefined);
    });
  }
  async function supervise() {
    if (!novice || !id) return;
    await task('Tracking and reviewing the novice recording…', async () => {
      const f = new FormData();
      f.set('video', novice);
      f.set('protocol_id', id);
      const result = await json<{ run_id: string }>('/api/runs', { method: 'POST', body: f });
      const done = await poll<Run & { status: string }>(`/api/runs/${result.run_id}`);
      onRun(done);
    });
  }
  return (
    <div className="learn-layout">
      {readOnly ? (
        <section className="panel learn-input">
          <h2>Learn from one demonstration</h2>
          <p className="muted">
            Inspect the sample protocol and its pending validation checks. Sign in to upload and
            analyse your own recordings.
          </p>
          <button className="button primary full" onClick={onSignIn}>
            Sign in to upload a recording
          </button>
        </section>
      ) : (
        <section className="panel learn-input">
          <div className="section-heading">
            <h2>Learn from one demonstration</h2>
            <FileVideo size={21} />
          </div>
          <p className="muted">
            The expert proposes a procedure. Four checks decide whether it is verified.
          </p>
          {!live && (
            <div className="notice">
              <Clock3 size={18} />
              <p>
                The analysis service is not connected on this installation. Explore the sample
                protocol on the right. It is a handwritten engineering fixture.
              </p>
            </div>
          )}
          <div className="notice">
            <FileVideo size={18} />
            <div>
              <strong>Reference demonstration · Science Buddies</strong>
              <p>
                <a
                  href="https://www.youtube.com/watch?v=gmeCY7ANrog"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Watch How to Make a Serial Dilution <ArrowUpRight size={14} />
                </a>
                {' · '}
                <a
                  href="https://www.sciencebuddies.org/science-fair-projects/references/how-to-make-a-dilution"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Original tutorial
                </a>
              </p>
              <p>
                External reference. For analysis, upload a recording you have permission to use.
              </p>
            </div>
          </div>
          <FileInput label="Expert A / compile recording" file={expert} onFile={setExpert} />
          <label className="field-label" htmlFor="narration">
            Timestamped narration JSON <span>optional if video has audio</span>
          </label>
          <textarea
            id="narration"
            value={narration}
            onChange={(e) => setNarration(e.target.value)}
            spellCheck={false}
            rows={3}
          />
          <p className="field-help">
            [{`{"start":0,"end":5,"text":"Position the dropper…"}`}]. Audio extraction requires
            ffmpeg.
          </p>
          <button
            className="button primary full"
            onClick={() => void compile()}
            disabled={!live || !expert || !!busy}
          >
            <Upload size={16} />
            Compile protocol
          </button>
          <hr />
          <h3>Validate with a second expert take</h3>
          <FileInput label="Expert B / held-out recording" file={heldout} onFile={setHeldout} />
          <label className="field-label" htmlFor="ranges">
            Review step timings <span>seconds in the original example video</span>
          </label>
          <textarea
            id="ranges"
            rows={5}
            value={ranges}
            onChange={(e) => {
              setRanges(e.target.value);
              setRangesConfirmed(false);
            }}
            spellCheck={false}
          />
          <p className="field-help">
            {boundaryNote ||
              'Compile an example to suggest timings from its narration. Fill any unmatched steps yourself.'}
          </p>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={rangesConfirmed}
              onChange={(e) => setRangesConfirmed(e.target.checked)}
            />
            I checked every start and end against the video and filled any missing times
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={repair} onChange={(e) => setRepair(e.target.checked)} />
            Allow up to 3 model repair rounds within budget
          </label>
          <button
            className="button full"
            disabled={!live || !id || !heldout || !rangesConfirmed || !!busy}
            onClick={() => void validate()}
          >
            Run four validation checks <ArrowUpRight size={15} />
          </button>
          <hr />
          <h3>Supervise a novice take</h3>
          <FileInput label="Novice recording" file={novice} onFile={setNovice} />
          <button
            className="button full"
            disabled={!live || !id || !novice || !!busy}
            onClick={() => void supervise()}
          >
            Analyze recording <ArrowUpRight size={15} />
          </button>
          {id && <p className="field-help mono">Protocol ID: {id}</p>}
          {busy && (
            <p className="notice" role="status">
              <span className="spinner" />
              {busy}
            </p>
          )}
          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}
        </section>
      )}
      <section className="panel learned-protocol">
        <div className="section-heading">
          <h2>{protocol.name}</h2>
          <button
            className="text-button"
            onClick={() => download('protocol.json', JSON.stringify(protocol, null, 2))}
          >
            Export JSON <ArrowUpRight size={15} />
          </button>
        </div>
        <p className="muted">
          {id
            ? 'Compiled from an uploaded recording. Source authenticity and validation are separate.'
            : 'Sample checklist · animated example · not learned from a real video.'}
        </p>
        <div className="validation-checks">
          {checks.map(([key, title, description]) => {
            const value = validation?.checks[key];
            return (
              <div
                key={key}
                className={value === true ? 'passed' : value === false ? 'failed' : 'pending'}
              >
                {value === true ? <CheckCircle2 size={19} /> : <Clock3 size={19} />}
                <div>
                  <strong>{title}</strong>
                  <small>{description}</small>
                </div>
                <span>{value === true ? 'PASS' : value === false ? 'FAIL' : 'PENDING'}</span>
              </div>
            );
          })}
        </div>
        <p className="field-help">
          Verified: {protocol.verified ? 'yes' : 'no'} · repair rounds:{' '}
          {validation?.repair_rounds ?? 0}. {validation?.scope ?? 'Real expert validation pending.'}
        </p>
        <div className="protocol-cards">
          {protocol.steps.map((s, i) => (
            <article key={s.id}>
              <div className="section-heading">
                <h3>
                  <span className="small-number">{i + 1}</span>
                  {s.title}
                </h3>
                <span className="mono">{s.id}</span>
              </div>
              <p>{s.narration_hint}</p>
              <details>
                <summary className="rule-label">Show the completion rule (JSON)</summary>
                <pre>{JSON.stringify(s.post, null, 2)}</pre>
              </details>
              <p className="field-help">
                Dwell {s.min_dwell_s}–{s.max_dwell_s}s ·{' '}
                {s.group ? `unordered group ${s.group}` : 'ordered step'}
              </p>
            </article>
          ))}
        </div>
        <div className="notice">
          <EyeNote />
        </div>
      </section>
    </div>
  );
}
function FileInput({
  label,
  file,
  onFile,
}: {
  label: string;
  file: File | null;
  onFile: (f: File | null) => void;
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
        accept="video/mp4,video/quicktime"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
    </label>
  );
}
function EyeNote() {
  return (
    <p>
      Contact and placement are observable. Concentration, transferred volume, tightness of a cap,
      and sterility are outside this protocol.
    </p>
  );
}
