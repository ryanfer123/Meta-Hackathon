import { useEffect, useState } from 'react';
import { Activity, Clock3, ShieldCheck } from 'lucide-react';
import '../styles/analysis-progress.css';

export type JobProgress = {
  stage: string;
  completed: number;
  total: number;
  unit: string;
  started_at: number;
  updated_at: number;
  eta_seconds: number | null;
  estimate_scope: 'current-stage';
};
const duration = (seconds: number) =>
  seconds < 60 ? `${Math.max(1, Math.round(seconds))} sec` : `${Math.ceil(seconds / 60)} min`;

export function AnalysisProgress({
  message,
  progress,
}: {
  message: string;
  progress?: JobProgress;
}) {
  const [opened] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const stale = progress && now / 1000 - progress.updated_at > 30;
  const known = progress && progress.total > 0;
  const elapsed = Math.max(0, (now - (progress ? progress.started_at * 1000 : opened)) / 1000);
  return (
    <section className="analysis-progress" aria-label="Analysis progress" aria-busy="true">
      <div className="analysis-heading">
        <span className="analysis-icon">
          <Activity size={24} />
        </span>
        <div>
          <p className="analysis-eyebrow">Analysis in progress</p>
          <h2>{progress?.stage ?? message}</h2>
        </div>
        <span className="analysis-live">
          <span /> Working
        </span>
      </div>
      <div className="analysis-meter">
        <div className="analysis-count" role="status" aria-live="polite">
          <span>
            {known
              ? `${progress.completed} of ${progress.total} ${progress.unit} processed`
              : 'Waiting for the next stage update'}
          </span>
          {known && <strong>{Math.floor((progress.completed / progress.total) * 100)}%</strong>}
        </div>
        <progress
          aria-label="Current stage progress"
          max={known ? progress.total : undefined}
          value={known ? progress.completed : undefined}
        />
      </div>
      <div className="analysis-facts">
        <div>
          <Clock3 size={18} />
          <span>
            Time elapsed<strong>{duration(elapsed)}</strong>
          </span>
        </div>
        <div>
          <Activity size={18} />
          <span>
            Estimated time remaining
            <strong>
              {stale
                ? 'Waiting for a fresh update'
                : progress?.eta_seconds != null
                  ? `About ${duration(progress.eta_seconds)} for this stage`
                  : 'Estimating as work completes'}
            </strong>
          </span>
        </div>
      </div>
      <p className="analysis-explainer">
        {known
          ? 'The estimate uses the pace of completed work in this stage. Later checks and any repairs take additional time.'
          : 'Model response times vary. An estimate will appear once enough work has completed.'}
      </p>
      <div className="analysis-footer">
        <ShieldCheck size={17} />
        <span>
          No need to submit again.{' '}
          {progress
            ? 'You can check its status in My runs.'
            : 'Keep this tab open until the upload finishes.'}
        </span>
      </div>
    </section>
  );
}
