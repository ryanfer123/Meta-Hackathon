import { useId } from 'react';

export type TrackingMode = 'image' | 'video';

export function TrackingChoice({
  value,
  onChange,
  disabled = false,
}: {
  value: TrackingMode;
  onChange: (value: TrackingMode) => void;
  disabled?: boolean;
}) {
  const help = useId();
  return (
    <div className="tracking-choice">
      <label className="checkbox">
        <input
          type="checkbox"
          checked={value === 'video'}
          onChange={(event) => onChange(event.target.checked ? 'video' : 'image')}
          disabled={disabled}
          aria-describedby={help}
        />
        Faster video tracking (preview)
      </label>
      <p id={help} className="field-help">
        Sends one video request per object description instead of one per sampled frame. If no
        objects are found, it tries image tracking within the same spending limit. Unclear objects
        stay unconfirmed. Speed varies; recordings are limited to 90 seconds in either mode.
      </p>
    </div>
  );
}
