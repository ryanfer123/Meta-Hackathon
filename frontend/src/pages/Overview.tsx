import { ArrowRight, Video, ScanLine, FileCheck2, FolderOpen } from 'lucide-react';
interface Props {
  onView: (view: string) => void;
  onSignIn: () => void;
  signedIn: boolean;
}
export function Overview({ onView, onSignIn, signedIn }: Props) {
  const start = () => (signedIn ? onView('Teach') : onSignIn());
  return (
    <div className="overview-page">
      <section className="overview-feature workflow-welcome">
        <div>
          <span className="home-eyebrow">Your workspace</span>
          <h2>Your next procedure starts here.</h2>
          <p>
            Show the right way in a teaching video. Check the next recording, then review what
            happened.
          </p>
          <div className="actions">
            <button className="button primary" onClick={start}>
              <Video size={18} /> Teach a procedure <ArrowRight size={18} />
            </button>
            {signedIn && (
              <button className="button" onClick={() => onView('My runs')}>
                <FolderOpen size={18} /> Open My runs
              </button>
            )}
          </div>
          <p className="field-help">
            A short, steady video with clearly visible objects is a good place to start.
          </p>
        </div>
        <div className="welcome-sequence" aria-label="Procedure workflow">
          <div>
            <Video size={21} />
            <span>Teaching video</span>
          </div>
          <span aria-hidden="true">↓</span>
          <div>
            <ScanLine size={21} />
            <span>New recording</span>
          </div>
          <span aria-hidden="true">↓</span>
          <div>
            <FileCheck2 size={21} />
            <span>Evidence and report</span>
          </div>
        </div>
      </section>
      <section className="overview-section" aria-labelledby="how-title">
        <h2 id="how-title">Three steps to a reviewable result</h2>
        <div className="how-strip">
          <article className="panel">
            <h3>1 Teach</h3>
            <p>Upload the right way.</p>
            <small>Review the proposed checklist and confirm each step's timing.</small>
          </article>
          <article className="panel">
            <h3>2 Check</h3>
            <p>Add another take.</p>
            <small>Track progress as objects and visible actions are checked.</small>
          </article>
          <article className="panel">
            <h3>3 Results</h3>
            <p>Inspect the evidence.</p>
            <small>Review findings at their timestamps and download the report.</small>
          </article>
        </div>
      </section>
    </div>
  );
}
