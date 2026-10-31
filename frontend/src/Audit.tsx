import { useEffect, useState } from 'react';
import { CheckCircle2, Copy, Download, ShieldCheck } from 'lucide-react';
import { download, verifyChain, exportReport } from './api';
import { checkedBy, friendlyEventLabel } from './eventLabels';
import { isAlert, timecode, type ChainEntry, type Event, type Run } from './types';
import './styles/results.css';
import { EventDetail } from './EventDetail';

const eventFields = (event: Event) => [
  event.t,
  event.step_id,
  event.kind,
  event.tier,
  event.confidence,
  event.detail,
  event.evidence_frame,
];
async function verifyReport(run: Run) {
  return (
    JSON.stringify(run.events.map(eventFields)) ===
      JSON.stringify(run.chain.map((entry) => eventFields(entry.event))) &&
    (await verifyChain(run.chain, run.chain_root))
  );
}

export function Audit({
  run,
  readOnly = false,
  onSignIn,
}: {
  run: Run;
  readOnly?: boolean;
  onSignIn?: () => void;
}) {
  const [root, setRoot] = useState(run.chain_root),
    [chain, setChain] = useState<ChainEntry[]>(run.chain),
    [integrity, setIntegrity] = useState<'checking' | 'unchanged' | 'changed' | 'unavailable'>(
      'checking',
    ),
    [manualResult, setManualResult] = useState(''),
    [downloadError, setDownloadError] = useState(''),
    [copied, setCopied] = useState(false),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setRoot(run.chain_root);
    setChain(run.chain);
    setManualResult('');
    setIntegrity('checking');
    setCopied(false);
    void verifyReport(run)
      .then((valid) => {
        if (active) setIntegrity(valid ? 'unchanged' : 'changed');
      })
      .catch(() => {
        if (active) setIntegrity('unavailable');
      });
    return () => {
      active = false;
    };
  }, [run]);
  async function verify() {
    setBusy(true);
    try {
      setManualResult(
        (await verifyChain(chain, root.trim()))
          ? 'Chain matches this root. Keep the root separately.'
          : 'Verification failed: event data, chain order, or root differs.',
      );
    } catch {
      setManualResult('Verification failed: invalid chain file.');
    } finally {
      setBusy(false);
    }
  }
  async function copyRoot() {
    try {
      await navigator.clipboard.writeText(run.chain_root);
      setCopied(true);
    } catch {
      setDownloadError(
        'Copy is unavailable in this browser. Open Advanced to select or download the root.',
      );
    }
  }
  const synthetic = run.provenance === 'synthetic';
  return (
    <div className="results-integrity">
      <section className="panel integrity-summary">
        <div className="section-heading">
          <h2>Report integrity</h2>
          <ShieldCheck size={24} />
        </div>
        <p className={`integrity-verdict ${integrity}`} role="status">
          {integrity === 'checking'
            ? 'Checking this report…'
            : integrity === 'unchanged'
              ? 'Report unchanged since it was created ✓'
              : integrity === 'changed'
                ? 'This report was changed ✗'
                : 'Could not check this report. Try a secure browser connection.'}
        </p>
        <p>
          This checks the event log against the report’s saved root. It does not prove that the
          recording is authentic or that the physical procedure was correct.
        </p>
        <p className="integrity-note">
          A local report can be rewritten together with its root. Keep the root somewhere separate.
        </p>
        <div className="actions">
          <a
            className="button primary"
            download={`${run.id}-report.html`}
            href={
              synthetic
                ? `${import.meta.env.BASE_URL}samples/${run.id.replace('sample-', '')}.html`
                : `/api/runs/${run.id}/report`
            }
            onClick={
              synthetic
                ? undefined
                : (event) => {
                    event.preventDefault();
                    void exportReport(run.id).catch(() =>
                      setDownloadError('Report download failed. Sign in again or retry.'),
                    );
                  }
            }
          >
            <Download size={16} />
            Download report (HTML)
          </a>
          <button className="button" onClick={() => void copyRoot()}>
            <Copy size={16} />
            {copied ? 'Root copied' : 'Copy root'}
          </button>
        </div>
        {downloadError && (
          <p role="alert" className="error-message">
            {downloadError}
          </p>
        )}
      </section>
      <details className="panel results-advanced integrity-advanced">
        <summary>Advanced: verification, model details and event history</summary>
        <section className="integrity-manual">
          <h3>Check against a root you kept separately</h3>
          <p className="muted">
            Changing this field checks a different root. It does not change the saved report.
          </p>
          <label className="field-label" htmlFor="root-hash">
            Expected root hash
          </label>
          <textarea
            id="root-hash"
            value={root}
            onChange={(event) => {
              setRoot(event.target.value);
              setManualResult('');
            }}
            rows={3}
            spellCheck={false}
          />
          {readOnly ? (
            <button className="text-button" onClick={onSignIn}>
              Sign in to load your own chain
            </button>
          ) : (
            <label className="chain-upload">
              Load a chain JSON to check
              <input
                aria-label="Load audit chain"
                type="file"
                accept="application/json,.json"
                onChange={async (event) => {
                  try {
                    const file = event.target.files?.[0];
                    if (file) {
                      setChain(JSON.parse(await file.text()));
                      setManualResult('Chain loaded; ready to verify.');
                    }
                  } catch {
                    setManualResult('Invalid JSON file.');
                  }
                }}
              />
            </label>
          )}
          <button className="button" onClick={() => void verify()} disabled={busy}>
            <CheckCircle2 size={16} />
            {busy ? 'Verifying…' : 'Verify chain'}
          </button>
          {manualResult && (
            <p
              className={
                manualResult.startsWith('Verification failed') ? 'error-message' : 'notice'
              }
              role="status"
            >
              {manualResult}
            </p>
          )}
          <div className="actions">
            <button
              className="button"
              onClick={() => download(`${run.id}-chain.json`, JSON.stringify(run.chain, null, 2))}
            >
              <Download size={16} />
              Export chain
            </button>
            <button
              className="button"
              onClick={() => download(`${run.id}-root.txt`, run.chain_root + '\n', 'text/plain')}
            >
              <Download size={16} />
              Save root
            </button>
          </div>
          <p className="field-help">
            Checking the evidence pixels also requires the original evidence files.
          </p>
        </section>
        <section className="audit-metrics">
          <h3>Model and source details</h3>
          <p>
            <span>Model second-opinion agreement</span>
            <strong>
              {run.metrics.shadow_agreement === null
                ? 'Not measured'
                : `${(run.metrics.shadow_agreement * 100).toFixed(1)}%`}
            </strong>
          </p>
          <p>
            <span>Cloud frame transmissions</span>
            <strong>
              {run.metrics.egress_percent === null
                ? 'Not measured'
                : `${run.metrics.egress_percent.toFixed(1)}%`}
            </strong>
          </p>
          <p>
            <span>Provenance</span>
            <strong>{run.provenance}</strong>
          </p>
          <p>
            <span>Open-model label</span>
            <strong>{run.metrics.open_tier_label ?? 'Not recorded'}</strong>
          </p>
          <p className="field-help">{run.metrics.note}</p>
        </section>
        <section className="ledger audit-ledger">
          <h3>Complete event history</h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Step</th>
                  <th>Result</th>
                  <th>What was seen</th>
                  <th>Checked by</th>
                </tr>
              </thead>
              <tbody>
                {run.events.map((event, index) => (
                  <tr key={index} className={isAlert(event.kind) ? 'deviation-row' : ''}>
                    <td className="mono">{timecode(event.t)}</td>
                    <td>
                      {run.protocol.steps.find((step) => step.id === event.step_id)?.title ??
                        'Run review'}
                    </td>
                    <td className="decision" title={event.kind}>
                      {friendlyEventLabel(event.kind)}
                    </td>
                    <td>
                      <EventDetail event={event} />
                    </td>
                    <td>
                      <span className="tier">
                        {checkedBy(event.tier, run.metrics.open_tier_label)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </details>
    </div>
  );
}
