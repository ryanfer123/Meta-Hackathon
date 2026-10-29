import { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
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
import { isAlert, label, timecode, type Event, type Run } from './types';
export function Supervise({ run, onAudit }: { run: Run; onAudit: () => void }) {
  const [time, setTime] = useState(0),
    [playing, setPlaying] = useState(false),
    [masks, setMasks] = useState(true),
    [sound, setSound] = useState(false),
    [selected, setSelected] = useState<string | null>(null);
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
    const firstAlert = run.events.find((event) => isAlert(event.kind));
    setTime(firstAlert?.t ?? 0);
    setPlaying(false);
    setSelected(firstAlert?.step_id ?? null);
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
  const selectedStep = run.protocol.steps.find((s) => s.id === selected);
  return (
    <>
      <div className="workstation">
        <section className="viewer panel" aria-label="Procedure playback">
          <div className="panel-meta">
            <span>{synthetic ? 'SIMULATED SCENE' : 'UPLOADED RECORDING'}</span>
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
                    title={`${label(e.kind)} at ${timecode(e.t)}`}
                    aria-label={`Seek to ${label(e.kind)}`}
                    style={{ left: `${(100 * e.t) / run.duration}%` }}
                    onClick={() => seek(e.t)}
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
            Protocol <span>/ {String(run.protocol.steps.length).padStart(2, '0')} steps</span>
          </h2>
          <div className="steps">
            {run.protocol.steps.map((s, i) => {
              const state = states[s.id] ?? 'PENDING';
              return (
                <button
                  key={s.id}
                  className={`step ${state.toLowerCase()} ${selected === s.id ? 'selected' : ''}`}
                  onClick={() => setSelected(selected === s.id ? null : s.id)}
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
          {selectedStep && (
            <div className="predicate-detail">
              <span>RULE / {selectedStep.id}</span>
              <pre>
                {JSON.stringify({ action: selectedStep.action, post: selectedStep.post }, null, 2)}
              </pre>
              <p>Only observed predicates can complete this step.</p>
            </div>
          )}
          <div className={latest ? 'alert' : 'observation'} role="status" aria-live="polite">
            {latest ? (
              <>
                <span className="alert-icon">
                  <AlertTriangle size={19} />
                </span>
                <div>
                  <strong>{label(latest.kind)}</strong>
                  <p>{latest.detail}</p>
                  <button className="text-button" onClick={() => seek(latest.t)}>
                    Inspect at {timecode(latest.t)} <ChevronRight size={13} />
                  </button>
                </div>
              </>
            ) : (
              <>
                <span className="status-dot" />
                <div>
                  <strong>{playing ? 'Observing procedure' : 'Ready to observe'}</strong>
                  <p>
                    {synthetic
                      ? 'Play the replay or seek to an event.'
                      : 'Play the recording to inspect decisions.'}
                  </p>
                </div>
              </>
            )}
          </div>
          <p className="advisory">
            {synthetic
              ? 'Model tiers are not exercised in synthetic replay.'
              : 'Model opinions are advisory. Rules decide completion.'}
          </p>
        </aside>
      </div>
      <section className="ledger panel">
        <div className="section-heading">
          <h2>
            Evidence ledger <span>/ {events.length} events</span>
          </h2>
          <button className="text-button" onClick={onAudit}>
            Open audit <ChevronRight size={15} />
          </button>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Observation</th>
                <th>Decision</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr>
                  <td>{timecode(0)}</td>
                  <td>Scene initialized. Play to observe the procedure.</td>
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
                    onSeek={() => seek(e.t)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
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
      <td className="decision">{label(e.kind)}</td>
      <td>
        <span className="tier">{e.tier === 'glimmer' ? openTierLabel : e.tier}</span>
        <small className="source-note">{synthetic ? 'synthetic masks' : 'recorded evidence'}</small>
      </td>
    </tr>
  );
}
