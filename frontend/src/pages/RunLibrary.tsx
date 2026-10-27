import { useEffect, useState } from 'react';
import {
  ArrowRight,
  CloudUpload,
  FileVideo,
  FolderOpen,
  LockKeyhole,
  Play,
  Trash2,
} from 'lucide-react';
import {
  deleteRecording,
  deleteSavedRun,
  listRecordings,
  listAnalysisJobs,
  recordingFile,
  type AnalysisJob,
  listRuns,
  openSavedRun,
  recordingUrl,
  uploadRecording,
  type Recording,
  type SavedRun,
} from '../lib/workspace';
import { Dialog } from '../components/Dialog';
import type { Run } from '../types';

interface Props {
  userId?: string;
  onSignIn: () => void;
  onOpen: (run: Run) => void;
  refreshKey: number;
  onUse: (file: File, kind: Recording['kind']) => void;
  onResume: (job: AnalysisJob) => void;
}
export function RunLibrary({ userId, onSignIn, onOpen, refreshKey, onUse, onResume }: Props) {
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [runs, setRuns] = useState<SavedRun[]>([]),
    [recordings, setRecordings] = useState<Recording[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [version, setVersion] = useState(0),
    [file, setFile] = useState<File | null>(null),
    [kind, setKind] = useState<Recording['kind']>('expert'),
    [preview, setPreview] = useState<string | null>(null),
    [deleteTarget, setDeleteTarget] = useState<{
      type: 'run' | 'recording';
      record: SavedRun | Recording;
    } | null>(null);
  useEffect(() => {
    if (!userId) {
      setRuns([]);
      setRecordings([]);
      return;
    }
    let active = true;
    setBusy(true);
    setError('');
    void Promise.all([listRuns(), listRecordings(), listAnalysisJobs()])
      .then(([r, f, j]) => {
        if (active) {
          setRuns(r);
          setJobs(j);
          setRecordings(f);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [userId, refreshKey, version]);
  async function task(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The request could not finish. Try again.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="library-page">
      <div className="library-intro">
        <div>
          <h2>Your work, kept together.</h2>
          <p>Saved runs and recordings belong to your private account.</p>
        </div>
        <LockKeyhole size={27} />
      </div>
      {!userId ? (
        <div className="library-empty">
          <FolderOpen size={46} />
          <h3>A place for the next take.</h3>
          <p>
            Sign in to keep runs and upload recordings. The sample workspace stays available without
            an account.
          </p>
          <button className="button primary" onClick={onSignIn}>
            Sign in to your workspace <ArrowRight size={17} />
          </button>
        </div>
      ) : (
        <>
          {!!jobs.length && (
            <section className="library-section">
              <div className="section-heading">
                <h2>Analysis jobs</h2>
                <button className="text-button" onClick={() => setVersion((v) => v + 1)}>
                  Refresh jobs
                </button>
              </div>
              {jobs.map((job) => (
                <article className="saved-run" key={job.id}>
                  <div>
                    <strong>{job.kind === 'learn' ? 'Expert protocol' : 'Procedure review'}</strong>
                    <p>
                      {job.status} · {new Date(job.created_at).toLocaleString()}
                    </p>
                    {job.status === 'error' && (
                      <p>{String(job.result.error ?? 'Processing failed')}</p>
                    )}
                  </div>
                  {job.status === 'ready' && (
                    <button className="button" onClick={() => onResume(job)}>
                      Open result <ArrowRight size={15} />
                    </button>
                  )}
                </article>
              ))}
            </section>
          )}
          <section className="library-section">
            <div className="section-heading">
              <h2>
                Saved runs <span>{runs.length}</span>
              </h2>
              <button className="text-button" onClick={() => setVersion((v) => v + 1)}>
                Refresh
              </button>
            </div>
            {runs.length ? (
              <div className="saved-run-list">
                {runs.map((r) => (
                  <article className="saved-run" key={r.id}>
                    <span className="saved-run-icon">
                      <Play size={20} />
                    </span>
                    <div>
                      <strong>{r.name}</strong>
                      <p>
                        {r.provenance === 'synthetic' ? 'Synthetic replay' : 'Recorded run'} ·{' '}
                        {new Date(r.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <button
                      className="button"
                      disabled={busy}
                      onClick={() => void task(async () => onOpen(await openSavedRun(r.id)))}
                    >
                      Open run <ArrowRight size={15} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label={`Delete ${r.name}`}
                      disabled={busy}
                      onClick={() => setDeleteTarget({ type: 'run', record: r })}
                    >
                      <Trash2 size={18} />
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <div className="quiet-empty">
                <FolderOpen size={24} />
                <p>No saved runs yet. Open a sample and choose Save run.</p>
              </div>
            )}
          </section>
          <section className="library-section">
            <div className="section-heading">
              <h2>
                Recordings <span>{recordings.length}</span>
              </h2>
              <span className="library-caption">Private storage</span>
            </div>
            <div className="recording-upload">
              <CloudUpload size={27} />
              <div>
                <h3>Keep the source material.</h3>
                <p>
                  Upload expert and novice takes. Analysis starts separately, when the inference
                  service is connected.
                </p>
                <div className="upload-fields">
                  <label className="upload-file-label">
                    {file ? file.name : 'Choose MP4 or MOV'}
                    <input
                      aria-label="Recording file"
                      type="file"
                      accept="video/mp4,video/quicktime"
                      onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    />
                  </label>
                  <label className="sr-only" htmlFor="recording-kind">
                    Recording role
                  </label>
                  <select
                    id="recording-kind"
                    value={kind}
                    onChange={(e) => setKind(e.target.value as Recording['kind'])}
                  >
                    <option value="expert">Expert A</option>
                    <option value="held_out">Expert B / held out</option>
                    <option value="novice">Novice</option>
                  </select>
                  <button
                    className="button primary"
                    disabled={!file || busy}
                    onClick={() =>
                      void task(async () => {
                        if (file) {
                          await uploadRecording(file, kind, userId);
                          setFile(null);
                          setVersion((v) => v + 1);
                        }
                      })
                    }
                  >
                    Upload recording
                  </button>
                </div>
                <small>Up to 50 MB per recording. Files are not publicly accessible.</small>
              </div>
            </div>
            {recordings.map((r) => (
              <article className="saved-run" key={r.id}>
                <span className="saved-run-icon">
                  <FileVideo size={21} />
                </span>
                <div>
                  <strong>{r.name}</strong>
                  <p>
                    {r.kind.replace('_', ' ')} · {(r.size_bytes / 1024 / 1024).toFixed(1)} MB ·
                    Uploaded, analysis pending
                  </p>
                </div>
                <button
                  className="button"
                  disabled={busy}
                  onClick={() => void task(async () => onUse(await recordingFile(r), r.kind))}
                >
                  Use in Learn
                </button>
                <button
                  className="button"
                  disabled={busy}
                  onClick={() =>
                    void task(async () => setPreview(await recordingUrl(r.object_path)))
                  }
                >
                  Preview
                </button>
                <button
                  className="icon-button"
                  disabled={busy}
                  aria-label={`Delete ${r.name}`}
                  onClick={() => setDeleteTarget({ type: 'recording', record: r })}
                >
                  <Trash2 size={18} />
                </button>
              </article>
            ))}
          </section>
        </>
      )}
      {busy && (
        <p className="loading-note" role="status">
          <span className="spinner" />
          Syncing your workspace…
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {preview && (
        <Dialog title="Recording preview" onClose={() => setPreview(null)}>
          <video className="recording-preview" controls src={preview} />
          <p className="field-help">This private playback link expires after one minute.</p>
        </Dialog>
      )}
      {deleteTarget && (
        <Dialog title={`Delete ${deleteTarget.type}?`} onClose={() => setDeleteTarget(null)}>
          <p className="dialog-description">
            This removes “{deleteTarget.record.name}” from your account. A recording's stored file
            is removed too.
          </p>
          <div className="actions">
            <button className="button" onClick={() => setDeleteTarget(null)}>
              Keep it
            </button>
            <button
              className="button danger"
              onClick={() => {
                const target = deleteTarget;
                setDeleteTarget(null);
                void task(async () => {
                  if (target.type === 'run') await deleteSavedRun(target.record.id);
                  else await deleteRecording(target.record as Recording);
                  setVersion((v) => v + 1);
                });
              }}
            >
              Delete {deleteTarget.type}
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
