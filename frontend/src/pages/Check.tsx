import { useEffect, useState } from 'react';
import { ArrowRight, Upload } from 'lucide-react';
import { json } from '../api';
import { pollJob } from '../lib/analysis';
import { ErrorNotice } from '../components/ErrorNotice';
import { AnalysisProgress, type JobProgress } from '../components/AnalysisProgress';
import type { Health, Protocol, Run } from '../types';
export type TaughtProcedure = { id: string; protocol: Protocol };
interface Props {
  procedure: TaughtProcedure | null;
  health: Health;
  readOnly?: boolean;
  source?: File | null;
  onTeach: () => void;
  onSample: () => void;
  onSignIn: () => void;
  onRun: (run: Run) => void;
}
export function CheckRecording({
  procedure,
  health,
  readOnly = false,
  source,
  onTeach,
  onSample,
  onSignIn,
  onRun,
}: Props) {
  const [file, setFile] = useState<File | null>(source ?? null);
  const [busy, setBusy] = useState('');
  const [progress, setProgress] = useState<JobProgress>();
  const [error, setError] = useState<unknown>('');
  useEffect(() => {
    if (source) setFile(source);
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
          <button className="button" onClick={onSample}>
            Use the sample steps
          </button>
        </div>
        <p className="field-help">
          Example steps are for exploring the animated sample. Your own recordings need a procedure
          you have taught.
        </p>
      </section>
    );
  const live = !health.replay_mode && health.live_configured;
  const reason = readOnly
    ? 'Sign in to check your own recording.'
    : busy
      ? busy
      : !live
        ? "Analysis isn't connected here — try the sample."
        : !file
          ? 'Add a recording to continue.'
          : '';
  async function check() {
    if (readOnly) {
      onSignIn();
      return;
    }
    if (!file || !procedure?.id || !live || busy) return;
    setError('');
    setBusy('Uploading the recording…');
    setProgress(undefined);
    try {
      const form = new FormData();
      form.set('video', file);
      form.set('protocol_id', procedure.id);
      const started = await json<{ run_id: string }>('/api/runs', { method: 'POST', body: form });
      setBusy('Checking the objects and steps…');
      const result = await pollJob<
        Run & { status?: string; error?: string; progress?: JobProgress }
      >(`/api/runs/${started.run_id}`, (update) => setProgress(update.progress));
      onRun(result);
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
      {readOnly ? (
        <button className="button" onClick={onSignIn}>
          Sign in to upload a recording
        </button>
      ) : (
        <label className="file-input">
          <Upload size={20} />
          <span>
            <strong>New recording</strong>
            <small>{file?.name ?? 'Choose MP4 / MOV · up to 90 seconds'}</small>
          </span>
          <input
            aria-label="New recording"
            type="file"
            accept="video/mp4,video/quicktime"
            disabled={!!busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
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
