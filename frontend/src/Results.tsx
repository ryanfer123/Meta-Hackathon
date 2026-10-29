import { useEffect, useState } from 'react';
import { Audit } from './Audit';
import { Supervise } from './Supervise';
import type { Run } from './types';
import './styles/results.css';

type ResultTab = 'Replay' | 'Integrity';
type ModelCall = {
  tier?: string;
  model?: string;
  latency_ms?: number;
  cloud_frames?: number;
  local_frames?: number;
  usage?: { video_frames_processed?: number };
};
type ObservedMetrics = Run['metrics'] & {
  calls?: ModelCall[];
  tier_distribution?: Record<string, number>;
};
function median(values: number[]): number | null {
  const sorted = values
    .filter((value) => Number.isFinite(value) && value >= 0)
    .sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}
function ModelChips({ run }: { run: Run }) {
  const metrics = run.metrics as ObservedMetrics;
  const calls = Array.isArray(metrics.calls) ? metrics.calls : undefined;
  const sparkCalls =
    calls?.filter((call) => call.tier === 'spark').length ?? metrics.tier_distribution?.spark;
  const samCalls = calls?.filter((call) => call.tier === 'sam');
  const samFrames = samCalls?.every((call) => typeof call.cloud_frames === 'number')
    ? samCalls.reduce((sum, call) => sum + (call.cloud_frames ?? 0), 0)
    : null;
  const opinions = (
    run as Run & { shadow?: { tier: string; available: boolean }[] }
  ).shadow?.filter((opinion) => opinion.tier === 'glimmer' && opinion.available).length;
  const openCalls =
    calls?.filter((call) => call.tier === metrics.open_tier_label || call.tier === 'glimmer')
      .length ??
    (metrics.open_tier_label ? metrics.tier_distribution?.[metrics.open_tier_label] : undefined);
  const latency = calls
    ? median(
        calls.flatMap((call) => (typeof call.latency_ms === 'number' ? [call.latency_ms] : [])),
      )
    : undefined;
  return (
    <div className="models-used" aria-label="Models used">
      <span>Models used</span>
      {typeof sparkCalls === 'number' && sparkCalls > 0 && (
        <span className="result-chip">
          Spark · {sparkCalls} {sparkCalls === 1 ? 'call' : 'calls'}
        </span>
      )}
      {samCalls && samCalls.length > 0 && (
        <span className="result-chip">
          SAM 3.1 ·{' '}
          {samFrames === null
            ? `${samCalls.length} ${samCalls.length === 1 ? 'call' : 'calls'}`
            : `${samFrames} ${samFrames === 1 ? 'frame' : 'frames'} sent`}
        </span>
      )}
      {metrics.open_tier_label &&
        ((typeof opinions === 'number' && opinions > 0) ||
          (typeof openCalls === 'number' && openCalls > 0)) && (
          <span className="result-chip">
            Open model ({metrics.open_tier_label}) ·{' '}
            {typeof opinions === 'number' && opinions > 0
              ? `${opinions} second ${opinions === 1 ? 'opinion' : 'opinions'}`
              : `${openCalls} ${openCalls === 1 ? 'call' : 'calls'}`}
          </span>
        )}
      {typeof latency === 'number' && Number.isFinite(latency) && latency >= 0 && (
        <span className="result-chip">Median response · {(latency / 1000).toFixed(2)} s</span>
      )}
      {!calls && !metrics.tier_distribution && (
        <span className="muted">Call details were not recorded.</span>
      )}
    </div>
  );
}
export function Results({
  run,
  initialTab = 'Replay',
  onTabChange,
  readOnly = false,
  onSignIn,
}: {
  run: Run;
  initialTab?: ResultTab;
  onTabChange?: (tab: ResultTab) => void;
  readOnly?: boolean;
  onSignIn?: () => void;
}) {
  const [tab, setTab] = useState<ResultTab>(initialTab);
  useEffect(() => setTab(initialTab), [initialTab, run.id]);
  function choose(next: ResultTab) {
    setTab(next);
    onTabChange?.(next);
  }
  return (
    <div className="results-page">
      {run.provenance === 'synthetic' ? (
        <div className="results-provenance" role="note">
          Example run — no real video and no models were involved.
        </div>
      ) : (
        <>
          <div className="results-provenance">Recorded run · {run.name}</div>
          <ModelChips run={run} />
        </>
      )}
      {run.provenance === 'synthetic' && (
        <p className="muted results-accuracy">
          Real-world accuracy hasn’t been measured on this example.
        </p>
      )}
      <div className="results-tabs" role="tablist" aria-label="Results views">
        {(['Replay', 'Integrity'] as const).map((name) => (
          <button
            key={name}
            id={`results-tab-${name.toLowerCase()}`}
            role="tab"
            aria-selected={tab === name}
            aria-controls={`results-panel-${name.toLowerCase()}`}
            tabIndex={tab === name ? 0 : -1}
            onClick={() => choose(name)}
            onKeyDown={(event) => {
              if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
                event.preventDefault();
                const next =
                  event.key === 'Home'
                    ? 'Replay'
                    : event.key === 'End'
                      ? 'Integrity'
                      : name === 'Replay'
                        ? 'Integrity'
                        : 'Replay';
                choose(next);
                document.getElementById(`results-tab-${next.toLowerCase()}`)?.focus();
              }
            }}
          >
            {name}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`results-panel-${tab.toLowerCase()}`}
        aria-labelledby={`results-tab-${tab.toLowerCase()}`}
      >
        {tab === 'Replay' ? (
          <Supervise run={run} onAudit={() => choose('Integrity')} />
        ) : (
          <Audit run={run} readOnly={readOnly} onSignIn={onSignIn} />
        )}
      </div>
    </div>
  );
}
