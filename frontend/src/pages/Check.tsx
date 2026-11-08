import { ClipSelector, appendClip, clipReason, type ClipRange } from '../components/ClipSelector';
import { useEffect, useState } from 'react';
import { ArrowRight, Upload } from 'lucide-react';
import { json } from '../api';
import { ObjectPreview, type ObjectPreviewData } from '../components/ObjectPreview';
import { uploadLimitReason } from '../lib/upload-limits';
import { pollJob } from '../lib/analysis';
import { ErrorNotice } from '../components/ErrorNotice';
import { AnalysisProgress, type JobProgress } from '../components/AnalysisProgress';
import { TrackingChoice, type TrackingMode } from '../components/TrackingChoice';
import type { Health, Protocol, Run } from '../types';
export type TaughtProcedure = { id: string; protocol: Protocol };
interface Props {
  procedure: TaughtProcedure | null;
  health: Health;
  readOnly?: boolean;
  source?: File | null;
  initialPreview?: ObjectPreviewData | null;
  onTeach: () => void;
  onSample?: () => void;
  onSignIn: () => void;
  onRun: (run: Run) => void;
}
export function CheckRecording({
  procedure,
  health,
  readOnly = false,
  source,
  initialPreview,
  onTeach,
  onSample,
  onSignIn,
  onRun,
}: Props) {
  const [clip, setClip] = useState<ClipRange | null>(null);
  const [file, setFile] = useState<File | null>(source ?? null);
  const [preview, setPreview] = useState<ObjectPreviewData | null>(initialPreview ?? null);
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  useEffect(() => {
    setPreview(initialPreview ?? null);
    setPrompts({});
    if(initialPreview?.next_tracking_mode) setTrackingMode(initialPreview.next_tracking_mode);
  }, [initialPreview]);
  const [busy, setBusy] = useState('');
  const [progress, setProgress] = useState<JobProgress>();
  const [error, setError] = useState<unknown>('');
  const [trackingMode, setTrackingMode] = useState<TrackingMode>('image');
  const nativeLimit = health.max_run_duration_s ?? 90;
  useEffect(() => {
    if (source) {
      setFile(source);
      setClip(null);
      setPreview(null);
      setPrompts({});
    }
  }, [source]);
  if (!procedure?.id)
    return (
      <section className="panel check-page">
        <h2>First teach it a procedure</h2>
        <p>
          Start with a video showing the right way. Review those steps before checking another
          recording.
        </p>
        <div className="actions">
          <button className="button primary" onClick={onTeach}>
            Go to Teach
          </button>
          {onSample && (
            <button className="button" onClick={onSample}>
              Use the sample steps
            </button>
          )}
        </div>
        <p className="field-help">
          {onSample
            ? 'Example steps are for exploring the animated sample. Your own recordings need a procedure you have taught.'
            : 'Once you have reviewed the teaching steps, return here with another recording of the same procedure.'}
        </p>
      </section>
    );
  const live = !health.replay_mode && health.live_configured;
  const reason = readOnly
    ? 'Sign in to check your own recording.'
    : busy
      ? busy
      : !live
        ? onSample
          ? "Analysis isn't connected here — try the sample."
          : 'Analysis is unavailable. Check the service connection and try again.'
        : !file && !preview
          ? 'Add a recording to continue.'
          : trackingMode === 'image' && (preview?.duration_s ?? 0) > 90
            ? 'Choose faster video tracking for this recording, or upload a shorter section.'
          : clipReason(clip, trackingMode === 'video' ? nativeLimit : 90) ||
            uploadLimitReason(health, [file]);
  async function check(previewOnly = false) {
    if (readOnly) {
      onSignIn();
      return;
    }
    if ((!file && !preview) || !procedure?.id || reason) return;
    setError('');
    setBusy('Uploading the recording…');
    setProgress(undefined);
    try {
      const form = new FormData();
      if (file && !preview) form.set('video', file);
      appendClip(form, clip);
      if (previewOnly) form.set('preview_only', 'true');
      if (preview)
        form.set(
          'prompts',
          JSON.stringify({
            ...Object.fromEntries(preview.protocol.objects.map((o) => [o.name, o.sam_prompt])),
            ...prompts,
          }),
        );
      form.set('protocol_id', procedure.id);
      form.set('tracking_mode', trackingMode);
      const started = await json<{ run_id: string }>(
        preview ? `/api/runs/${preview.id}/analyse` : '/api/runs',
        { method: 'POST', body: form },
      );
      setBusy('Checking the objects and steps…');
      const result = await pollJob<
        Run & { status?: string; error?: string; progress?: JobProgress }
      >(`/api/runs/${started.run_id}`, (update) => setProgress(update.progress));
      if ((result as unknown as ObjectPreviewData).phase === 'object-preview') {
        setPreview(result as unknown as ObjectPreviewData);
        setPrompts({});
      } else onRun(result);
    } catch (e) {
      setError(e);
    } finally {
      setBusy('');
    }
  }
  return (
    <section className="panel check-page">
      <h2>Check a new recording</h2>
      <p>
        Compare it with <strong>{procedure.protocol.name}</strong> (
        {procedure.protocol.steps.length} steps).
      </p>
      <p className="field-help">
        Use one procedure per recording. Check repeated attempts as separate runs.
      </p>
      {readOnly ? (
        <button className="button" onClick={onSignIn}>
          Sign in to upload a recording
        </button>
      ) : (
        <label className="file-input">
          <Upload size={20} />
          <span>
            <strong>New recording</strong>
            <small>
              {file?.name ??
                `Choose MP4 / MOV · up to ${trackingMode === 'video' ? nativeLimit : 90} seconds`}
            </small>
          </span>
          <input
            aria-label="New recording"
            type="file"
            accept="video/mp4,video/quicktime"
            disabled={!!busy}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setClip(null);
              setPreview(null);
              setPrompts({});
            }}
          />
        </label>
      )}
      {!readOnly && !preview && (
        <ClipSelector
          file={file}
          label="New recording"
          value={clip}
          onChange={setClip}
          maximum={trackingMode === 'video' ? nativeLimit : 90}
          disabled={!!busy}
        />
      )}
      {!readOnly && (
        <TrackingChoice
          value={trackingMode}
          onChange={setTrackingMode}
          disabled={!!busy}
          maxSeconds={nativeLimit}
        />
      )}
      {preview && (
        <ObjectPreview
          preview={preview}
          disabled={!!busy}
          prompts={prompts}
          onPrompt={(name, value) => setPrompts((p) => ({ ...p, [name]: value }))}
        />
      )}
      {!readOnly && (
        <>
          <button
            className="button"
            disabled={!!reason}
            aria-describedby="check-disabled-reason"
            onClick={() => void check(true)}
          >
            {preview ? 'Preview objects again (paid)' : 'Preview objects (paid)'}
          </button>
          <p className="field-help">
            Up to {3 * procedure.protocol.objects.length} image segmentation requests for three
            frames, subject to the same job budget. Full analysis is a separate action.
          </p>
        </>
      )}
      <button
        className="button primary"
        disabled={!!reason}
        aria-describedby="check-disabled-reason"
        onClick={() => void check()}
      >
        Check this recording <ArrowRight size={16} />
      </button>
      <p id="check-disabled-reason" className="field-help" role={busy ? 'status' : undefined}>
        {reason || 'The recording will be checked against your reviewed steps.'}
      </p>
      <ErrorNotice error={error} />
      {busy && <AnalysisProgress message={busy} progress={progress} />}
    </section>
  );
}
