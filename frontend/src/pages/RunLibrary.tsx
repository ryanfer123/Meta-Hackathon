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
import { ErrorNotice } from '../components/ErrorNotice';
import type { Run } from '../types';

interface Props {
  userId?: string;
  onSignIn: () => void;
  onOpen: (run: Run) => void;
  refreshKey: number;
  onUse: (file: File, kind: Recording['kind']) => void;
  onResume: (job: AnalysisJob) => void;
}
type LibraryItem =
  | { type: 'job'; record: AnalysisJob }
  | { type: 'run'; record: SavedRun }
  | { type: 'recording'; record: Recording };
const recordingLabels: Record<Recording['kind'], string> = {
  expert: 'Teaching video',
  held_out: 'Second video',
  novice: 'New recording',
};
function jobName(job: AnalysisJob): string {
  if (typeof job.result.name === 'string' && job.result.name.trim()) return job.result.name;
  const protocol = job.result.protocol;
  if (
    protocol &&
    typeof protocol === 'object' &&
    'name' in protocol &&
    typeof protocol.name === 'string'
  )
    return protocol.name;
  return job.kind === 'learn' ? 'Teaching checklist' : 'Recording check';
}
function itemName(item: LibraryItem): string {
  return item.type === 'job' ? jobName(item.record) : item.record.name;
}
function itemType(item: LibraryItem): string {
  return item.type === 'recording'
    ? 'Recording'
    : item.type === 'job' && item.record.kind === 'learn'
      ? 'Protocol'
      : 'Run';
}
export function RunLibrary({ userId, onSignIn, onOpen, refreshKey, onUse, onResume }: Props) {
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [runs, setRuns] = useState<SavedRun[]>([]),
    [recordings, setRecordings] = useState<Recording[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(''),
    [version, setVersion] = useState(0),
    [file, setFile] = useState<File | null>(null),
    [kind, setKind] = useState<Recording['kind']>('expert'),
    [preview, setPreview] = useState<{ record: Recording; url: string } | null>(null),
    [deleteTarget, setDeleteTarget] = useState<{
      type: 'run' | 'recording';
      record: SavedRun | Recording;
    } | null>(null);
  useEffect(() => {
    if (!userId) {
      setJobs([]);
      setRuns([]);
      setRecordings([]);
      setPreview(null);
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
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const savedSources = new Set(runs.map((run) => run.source_run_id));
  const items: LibraryItem[] = [
    ...runs.map((record) => ({ type: 'run' as const, record })),
    ...recordings.map((record) => ({ type: 'recording' as const, record })),
    ...jobs
      .filter((job) => !(job.kind === 'run' && job.status === 'ready' && savedSources.has(job.id)))
      .map((record) => ({ type: 'job' as const, record })),
  ].sort(
    (a, b) =>
      Date.parse(b.record.created_at) - Date.parse(a.record.created_at) ||
      a.record.id.localeCompare(b.record.id),
  );
  async function open(item: LibraryItem) {
    if (item.type === 'job') onResume(item.record);
    else if (item.type === 'run') onOpen(await openSavedRun(item.record.id));
    else setPreview({ record: item.record, url: await recordingUrl(item.record.object_path) });
  }
  return (
    <div className="library-page">
      <div className="library-intro">
        <div>
          <h2>My runs</h2>
          <p>Your checklists, results and recordings, all private to your account.</p>
        </div>
        <LockKeyhole size={27} />
      </div>
      {!userId ? (
        <div className="library-empty">
          <FolderOpen size={46} />
          <h3>Keep your work here.</h3>
          <p>
            Sign in to save results and upload recordings. You can try the samples without an
            account.
          </p>
          <button className="button primary" onClick={onSignIn}>
            Sign in to your workspace <ArrowRight size={17} />
          </button>
        </div>
      ) : (
        <>
          <details className="library-section recording-add">
            <summary>
              <CloudUpload size={21} /> Add a recording
            </summary>
            <div className="recording-upload">
              <div>
                <p>
                  Store a video here, then open it to use in Teach or Check. Uploading alone does
                  not start analysis.
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
                    <option value="expert">Teaching video</option>
                    <option value="held_out">Second video</option>
                    <option value="novice">New recording</option>
                  </select>
                  <button
                    className="button primary"
                    disabled={!file || busy}
                    aria-describedby="recording-upload-reason"
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
                <p id="recording-upload-reason" className="field-help">
                  {busy
                    ? 'Wait for the current request to finish.'
                    : !file
                      ? 'Choose a recording to upload.'
                      : 'Ready to upload to your private storage.'}
                </p>
                <small>MP4 or MOV, up to 50 MB. Only your account can access these files.</small>
              </div>
            </div>
          </details>
          <section className="library-section" aria-label="Your saved work">
            <div className="section-heading">
              <h2>
                All work <span>{items.length}</span>
              </h2>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => setVersion((v) => v + 1)}
              >
                Refresh
              </button>
            </div>
            {items.length ? (
              <div className="saved-run-list">
                {items.map((item) => {
                  const name = itemName(item),
                    type = itemType(item);
                  const unavailable = item.type === 'job' && item.record.status !== 'ready';
                  const statusId = `library-status-${item.type}-${item.record.id}`;
                  return (
                    <article className="saved-run" key={`${item.type}-${item.record.id}`}>
                      <span className="saved-run-icon">
                        {item.type === 'recording' ? <FileVideo size={21} /> : <Play size={20} />}
                      </span>
                      <div>
                        <span className="library-item-type">{type}</span>
                        <strong>{name}</strong>
                        <p>
                          <time dateTime={item.record.created_at}>
                            {new Date(item.record.created_at).toLocaleString()}
                          </time>
                          {item.type === 'recording' && (
                            <>
                              {' '}
                              · {recordingLabels[item.record.kind]} ·{' '}
                              {(item.record.size_bytes / 1024 / 1024).toFixed(1)} MB
                            </>
                          )}
                          {item.type === 'run' && (
                            <>
                              {' '}
                              ·{' '}
                              {item.record.provenance === 'synthetic'
                                ? 'Animated sample'
                                : 'Recorded run'}
                            </>
                          )}
                        </p>
                        {item.type === 'job' && (
                          <p id={statusId}>
                            {item.record.status === 'processing'
                              ? 'Still processing. Refresh to check again.'
                              : item.record.status === 'error'
                                ? 'Could not finish. Try uploading the recording again.'
                                : 'Ready to open'}
                          </p>
                        )}
                      </div>
                      <button
                        className="button"
                        disabled={busy || unavailable}
                        aria-label={`Open ${name}`}
                        aria-describedby={unavailable ? statusId : undefined}
                        onClick={() => void task(() => open(item))}
                      >
                        Open <ArrowRight size={15} />
                      </button>
                      {item.type !== 'job' && (
                        <button
                          className="icon-button"
                          disabled={busy}
                          aria-label={`Delete ${name}`}
                          onClick={() => setDeleteTarget({ type: item.type, record: item.record })}
                        >
                          <Trash2 size={18} />
                        </button>
                      )}
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="quiet-empty">
                <FolderOpen size={24} />
                <p>No runs or recordings yet. Try a sample, or add a recording.</p>
              </div>
            )}
          </section>
        </>
      )}
      {busy && (
        <p className="loading-note" role="status">
          <span className="spinner" />
          Updating your work…
        </p>
      )}
      <ErrorNotice error={error} />
      {preview && (
        <Dialog title={preview.record.name} onClose={() => setPreview(null)}>
          <video className="recording-preview" controls src={preview.url} />
          <p className="field-help">Your private preview link expires after one minute.</p>
          <div className="actions">
            <button
              className="button"
              disabled={busy}
              onClick={() =>
                void task(async () => {
                  const record = preview.record;
                  const file = await recordingFile(record);
                  setPreview(null);
                  onUse(file, record.kind === 'held_out' ? 'held_out' : 'expert');
                })
              }
            >
              Use in Teach <ArrowRight size={15} />
            </button>
            <button
              className="button primary"
              disabled={busy}
              onClick={() =>
                void task(async () => {
                  const file = await recordingFile(preview.record);
                  setPreview(null);
                  onUse(file, 'novice');
                })
              }
            >
              Use in Check <ArrowRight size={15} />
            </button>
          </div>
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
