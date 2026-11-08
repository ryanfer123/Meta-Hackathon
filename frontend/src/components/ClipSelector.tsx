import '../styles/recording-tools.css';
import { useEffect, useRef, useState } from 'react';
export type ClipRange = { start: number; end: number; source_duration?: number };
export function clipReason(value: ClipRange | null, maximum: number): string {
  return value &&
    (!Number.isFinite(value.start) ||
      !Number.isFinite(value.end) ||
      value.start < 0 ||
      value.end - value.start < 1.5 ||
      value.end - value.start > maximum ||
      (value.source_duration !== undefined && value.end > value.source_duration))
    ? `Choose a section between 1.5 and ${maximum} seconds.`
    : '';
}
export function appendClip(form: FormData, value: ClipRange | null) {
  if (value) {
    form.set('trim_start_s', String(value.start));
    form.set('trim_end_s', String(value.end));
  }
}
export function ClipSelector({
  file,
  label,
  value,
  onChange,
  maximum,
  disabled = false,
}: {
  file: File | null;
  label: string;
  value: ClipRange | null;
  onChange: (v: ClipRange | null) => void;
  maximum: number;
  disabled?: boolean;
}) {
  const [url, setUrl] = useState(''),
    [duration, setDuration] = useState(0);
  const player = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    setDuration(0);
    if (!file) {
      setUrl('');
      return;
    }
    const url = URL.createObjectURL(file);
    setUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  if (!file) return null;
  return (
    <details className="clip-selector">
      <summary>Trim {label.toLowerCase()} to the procedure (optional)</summary>
      <p>
        Skip setup and idle time. The original recording stays private and findings keep its
        timestamps. Preparing a trimmed section adds an encoding step.
      </p>
      <video
        ref={player}
        controls
        preload="metadata"
        src={url}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        aria-label={`${label} section preview`}
      />
      <label>
        <input
          type="checkbox"
          disabled={disabled || !duration}
          checked={!!value}
          onChange={(e) =>
            onChange(
              e.target.checked
                ? { start: 0, end: Math.min(duration, maximum), source_duration: duration }
                : null,
            )
          }
        />
        Choose a section of {label.toLowerCase()}
      </label>
      {!duration && <p className="field-help">Load a playable video to choose a section.</p>}
      {value && (
        <fieldset disabled={disabled}>
          <legend>Section in original seconds</legend>
          <label>
            Start
            <input
              aria-label={`${label} section start`}
              type="number"
              min="0"
              max={duration}
              step="0.1"
              value={Number.isFinite(value.start) ? value.start : ''}
              onChange={(e) => onChange({ ...value, start: e.currentTarget.valueAsNumber })}
            />
          </label>
          <button
            type="button"
            className="button"
            onClick={() => onChange({ ...value, start: player.current?.currentTime ?? 0 })}
          >
            Mark section start here
          </button>
          <label>
            End
            <input
              aria-label={`${label} section end`}
              type="number"
              min="0"
              max={duration}
              step="0.1"
              value={Number.isFinite(value.end) ? value.end : ''}
              onChange={(e) => onChange({ ...value, end: e.currentTarget.valueAsNumber })}
            />
          </label>
          <button
            type="button"
            className="button"
            onClick={() => onChange({ ...value, end: player.current?.currentTime ?? 0 })}
          >
            Mark section end here
          </button>
          <p role="status">
            {clipReason(value, maximum) ||
              `${(value.end - value.start).toFixed(1)} seconds selected. Only this section will be analysed.`}
          </p>
        </fieldset>
      )}
    </details>
  );
}
