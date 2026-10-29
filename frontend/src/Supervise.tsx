import { useEffect, useRef, useState } from 'react';
import {
  Check,
  ChevronRight,
  Eye,
  EyeOff,
  Pause,
  Play,
  RotateCcw,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { privateMedia } from './api';
import { Scene } from './Scene';
import { isAlert, timecode, type Event, type Run } from './types';
import { checkedBy, flagReason, friendlyEventLabel } from './eventLabels';
import './styles/results.css';

const firstAlert = (run: Run) =>
  [...run.events].filter((event) => isAlert(event.kind)).sort((a, b) => a.t - b.t)[0];
export function Supervise({ run, onAudit }: { run: Run; onAudit: () => void }) {
  const [time, setTime] = useState(() => firstAlert(run)?.t ?? 0),
    [playing, setPlaying] = useState(false),
    [masks, setMasks] = useState(true),
    [sound, setSound] = useState(false),
    [selected, setSelected] = useState<string | null>(() => firstAlert(run)?.step_id ?? null),
    [selectedEvent, setSelectedEvent] = useState<Event | null>(() => firstAlert(run) ?? null);
  const video = useRef<HTMLVideoElement>(null),
    lastAlert = useRef('');
  const synthetic = run.provenance === 'synthetic';
  const [mediaUrl, setMediaUrl] = useState(''),
    [mediaError, setMediaError] = useState('');
  useEffect(() => {
    if (synthetic) return;
    let active = true,
      url = '';
    setMediaUrl('');
    setMediaError('');
    void privateMedia(`/api/media/${run.id}/original.mp4`)
      .then((value) => {
        url = value;
        if (active) setMediaUrl(value);
        else URL.revokeObjectURL(value);
      })
      .catch(() => {
        if (active)
          setMediaError('Private recording unavailable. Reopen the run or sign in again.');
      });
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [run.id, synthetic]);
  useEffect(() => {
    const initial = firstAlert(run);
    setTime(initial?.t ?? 0);
    setPlaying(false);
    setSelected(initial?.step_id ?? null);
    setSelectedEvent(initial ?? null);
    lastAlert.current = '';
  }, [run]);
  useEffect(() => {
    if (!playing || !synthetic) return;
    let last = performance.now();
    const timer = setInterval(() => {
      const now = performance.now(),
        delta = (now - last) / 1000;
      last = now;
      setTime((t) => {
        if (t + delta >= run.duration) {
          setPlaying(false);
          return run.duration;
        }
        return t + delta;
      });
    }, 100);
    return () => clearInterval(timer);
  }, [playing, run.duration, synthetic]);
  const events = run.events.filter((e) => e.t <= time),
    alerts = events.filter((e) => isAlert(e.kind));
  const priority: Record<string, number> = {
    skipped: 5,
    wrong_object: 4,
    out_of_order: 3,
    dwell_exceeded: 2,
    uncertain: 1,
  };
  const latest = alerts.reduce<Event | undefined>(
      (a, e) =>
        !a || e.t > a.t || (e.t === a.t && (priority[e.kind] ?? 0) > (priority[a.kind] ?? 0))
          ? e
          : a,
      undefined,
    ),
    alertKey = latest ? `${run.id}:${latest.step_id}:${latest.kind}:${latest.t}` : '';
  useEffect(() => {
    if (alertKey && alertKey !== lastAlert.current && sound) {
      const ctx = new AudioContext();
      const o = ctx.createOscillator(),
        g = ctx.createGain();
      o.connect(g);
      g.connect(ctx.destination);
      o.frequency.value = 520;
      g.gain.value = 0.07;
      o.start();
      o.stop(ctx.currentTime + 0.17);
      o.onended = () => void ctx.close();
    }
    lastAlert.current = alertKey;
  }, [alertKey, sound]);
  const markers = run.events
    .filter((e) => isAlert(e.kind))
    .reduce<Event[]>((all, e) => {
      const last = all.at(-1);
      if (last && e.t - last.t <= 2) {
        if ((priority[e.kind] ?? 0) > (priority[last.kind] ?? 0)) all[all.length - 1] = e;
      } else all.push(e);
      return all;
    }, []);
  const frame = [...run.frames].reverse().find((f) => f.t <= time) ?? run.frames[0];
  const states: Record<string, string> = {};
  for (const e of events) {
    if (e.step_id && e.kind === 'step_started') states[e.step_id] = 'ACTIVE';
    if (e.step_id && e.kind === 'step_completed') states[e.step_id] = 'DONE';
    if (e.step_id && e.kind === 'skipped') states[e.step_id] = 'SKIPPED';
  }
  function seek(t: number) {
    setTime(t);
    if (video.current) video.current.currentTime = t;
  }
  function toggle() {
    if (video.current) {
      if (playing) video.current.pause();
      else void video.current.play();
    }
    setPlaying(!playing);
  }
  function inspect(event: Event) {
    seek(event.t);
    setPlaying(false);
    video.current?.pause();
    setSelected(event.step_id);
    setSelectedEvent(event);
  }
  const selectedStep = run.protocol.steps.find((s) => s.id === selected);
  const flagged =
    selectedEvent && isAlert(selectedEvent.kind)
      ? selectedEvent
      : selected === null || latest?.step_id === selected
        ? latest
        : undefined;
  return (
    <>
      {flagged && (
        <section className="why-flagged" aria-label="Why this was flagged">
          <h3>Why this was flagged{selectedStep ? ` — ${selectedStep.title}` : ''}</h3>
          <strong title={flagged.kind}>{friendlyEventLabel(flagged.kind)}</strong>
          <p>{flagReason(flagged)}</p>
          <details>
            <summary>Show details</summary>
            <p>{flagged.detail}</p>
          </details>
          {selectedStep && (
            <p>
              <span className="muted">Expected:</span>{' '}
              {selectedStep.narration_hint || selectedStep.title}
            </p>
          )}
          <button className="text-button" onClick={() => inspect(flagged)}>
            View at {timecode(flagged.t)} <ChevronRight size={13} />
          </button>
          <small>Checked by: {checkedBy(flagged.tier, run.metrics.open_tier_label)}</small>
        </section>
      )}
      <div className="workstation">
        <section className="viewer panel" aria-label="Procedure playback">
          <div className="panel-meta">
            <span>{synthetic ? 'Example animation' : 'Your recording'}</span>
            <button className="text-button" onClick={() => setMasks(!masks)}>
              {masks ? <Eye size={14} /> : <EyeOff size={14} />}{' '}
              {masks ? 'Overlays on' : 'Overlays off'}
            </button>
          </div>
          {synthetic ? (
            <Scene frame={frame} masks={masks} />
          ) : (
            <div className="video-layer">
              {mediaError && <p role="alert">{mediaError}</p>}
              <video
                ref={video}
                src={mediaUrl || undefined}
                onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
                onLoadedMetadata={(e) => {
                  e.currentTarget.currentTime = time;
                }}
                onEnded={() => setPlaying(false)}
              />
              {masks && (
                <svg viewBox={`0 0 ${frame.width} ${frame.height}`} className="mask-overlay">
                  {Object.entries(frame.objects).map(
                    ([n, d]) =>
                      d && (
                        <g key={n}>
                          {d.contours.map((c, i) => (
                            <polygon
                              key={i}
                              points={c.map((p) => p.join(',')).join(' ')}
                              fill="#d5fa6520"
                              stroke="#d5fa65"
                              strokeWidth="2"
                            />
                          ))}
                          <text x={d.x} y={Math.max(18, d.y - 5)} fill="#d5fa65" fontSize="15">
                            {n}
                          </text>
                        </g>
                      ),
                  )}
                </svg>
              )}
            </div>
          )}
          <div className="playback">
            <button
              className="play-button"
              onClick={toggle}
              aria-label={playing ? 'Pause replay' : 'Play replay'}
            >
              {playing ? <Pause size={18} /> : <Play size={18} fill="currentColor" />}
            </button>
            <div className="timeline">
              <input
                aria-label="Replay position"
                type="range"
                min="0"
                max={run.duration}
                step="0.1"
                value={time}
                onChange={(e) => seek(Number(e.target.value))}
              />
              <div className="timeline-events">
                {markers.map((e, i) => (
                  <button
                    key={i}
                    title={`${e.kind} at ${timecode(e.t)}`}
                    aria-label={`Seek to ${friendlyEventLabel(e.kind)}`}
                    style={{ left: `${(100 * e.t) / run.duration}%` }}
                    onClick={() => inspect(e)}
                  />
                ))}
              </div>
            </div>
            <span className="timecode">
              {timecode(time)} <span>/ {timecode(run.duration)}</span>
            </span>
            <button
              className="icon-button"
              aria-label="Restart replay"
              onClick={() => {
                seek(0);
                setPlaying(false);
                video.current?.pause();
              }}
            >
              <RotateCcw size={16} />
            </button>
            <button
              className="icon-button"
              aria-label={sound ? 'Mute alerts' : 'Enable alert sound'}
              aria-pressed={sound}
              onClick={() => setSound(!sound)}
            >
              {sound ? <Volume2 size={17} /> : <VolumeX size={17} />}
            </button>
          </div>
        </section>
        <aside className="protocol panel">
          <h2>
            Checklist <span>/ {String(run.protocol.steps.length).padStart(2, '0')} steps</span>
          </h2>
          <div className="steps">
            {run.protocol.steps.map((s, i) => {
              const state = states[s.id] ?? 'PENDING';
              return (
                <button
                  key={s.id}
                  className={`step ${state.toLowerCase()} ${selected === s.id ? 'selected' : ''}`}
                  onClick={() => {
                    setSelected(s.id);
                    const event = [...run.events]
                      .reverse()
                      .find((event) => event.step_id === s.id && isAlert(event.kind));
                    setSelectedEvent(event ?? null);
                    if (event) inspect(event);
                  }}
                  aria-expanded={selected === s.id}
                >
                  <span className="step-number">
                    {state === 'DONE' ? <Check size={18} /> : state === 'SKIPPED' ? '!' : i + 1}
                  </span>
                  <span className="step-text">
                    <strong>{s.title}</strong>
                    <small>{s.narration_hint}</small>
                  </span>
                  <ChevronRight className="step-arrow" size={17} />
                </button>
              );
            })}
          </div>
          {!flagged && (
            <div className="observation" role="status">
              <span className="status-dot" />
              <div>
                <strong>{playing ? 'Playing the recording' : 'Ready — press play'}</strong>
                <p>
                  {synthetic
                    ? 'This is an animated example, not real video.'
                    : 'Select a step or play the recording to review it.'}
                </p>
              </div>
            </div>
          )}
          {selectedStep && (
            <details className="results-advanced predicate-detail">
              <summary>Advanced: rules for this step</summary>
              <pre>
                {JSON.stringify({ action: selectedStep.action, post: selectedStep.post }, null, 2)}
              </pre>
              <p>Only visible rule evidence can complete this step.</p>
              <p>
                Timing: {selectedStep.min_dwell_s}–{selectedStep.max_dwell_s} seconds.{' '}
                {selectedStep.group ? `Unordered group: ${selectedStep.group}` : 'Ordered step.'}
              </p>
            </details>
          )}
          <p className="advisory">
            {synthetic
              ? 'No models ran for this animated example.'
              : 'Models give a second opinion. Rules decide whether a step was observed.'}
          </p>
        </aside>
      </div>
      <details className="ledger panel results-advanced">
        <summary>Advanced: what happened</summary>
        <div className="section-heading">
          <h2>
            What happened <span>/ {events.length} events</span>
          </h2>
          <button className="text-button" onClick={onAudit}>
            Open integrity check <ChevronRight size={15} />
          </button>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>What was seen</th>
                <th>Result</th>
                <th>Checked by</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr>
                  <td>{timecode(0)}</td>
                  <td>Ready — press play.</td>
                  <td>Awaiting evidence</td>
                  <td>{synthetic ? 'Synthetic masks' : 'Video + masks'}</td>
                </tr>
              ) : (
                events.map((e, i) => (
                  <EvidenceRow
                    key={i}
                    event={e}
                    synthetic={synthetic}
                    openTierLabel={run.metrics.open_tier_label ?? 'glimmer'}
                    onSeek={() => inspect(e)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </details>
      <div className="footnote">
        <span>Models propose. Pixels ground. Code decides.</span>
        <span>Observable handling only · contact does not prove a pour.</span>
      </div>
    </>
  );
}
function EvidenceRow({
  event: e,
  synthetic,
  onSeek,
  openTierLabel,
}: {
  event: Event;
  synthetic: boolean;
  onSeek: () => void;
  openTierLabel: string;
}) {
  return (
    <tr className={isAlert(e.kind) ? 'deviation-row' : ''}>
      <td>
        <button className="text-button mono" onClick={onSeek}>
          {timecode(e.t)}
        </button>
      </td>
      <td>{e.detail}</td>
      <td className="decision" title={e.kind}>
        {friendlyEventLabel(e.kind)}
      </td>
      <td>
        <span className="tier">{checkedBy(e.tier, openTierLabel)}</span>
        <small className="source-note">{synthetic ? 'synthetic masks' : 'recorded evidence'}</small>
      </td>
    </tr>
  );
}
