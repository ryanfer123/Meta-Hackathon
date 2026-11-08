import '../styles/recording-tools.css';
import { useState } from 'react';
import type { Frame, Protocol } from '../types';
export type ObjectPreviewData = {
  id: string;
  phase: 'object-preview';
  next_tracking_mode?: 'image' | 'video';
  duration_s?: number;
  analysis_range?: { start: number; end: number } | null;
  protocol: Protocol;
  frames: (Frame & { image: string })[];
  objects: { name: string; visible_frames: number; total_frames: number }[];
};
export function ObjectPreview({
  preview,
  prompts,
  onPrompt,
  disabled = false,
}: {
  preview: ObjectPreviewData;
  prompts: Record<string, string>;
  onPrompt: (name: string, value: string) => void;
  disabled?: boolean;
}) {
  const [index, setIndex] = useState(0);
  const frame = preview.frames[Math.min(index, preview.frames.length - 1)];
  return (
    <section className="object-preview" aria-label="Object preview">
      <h3>Check the objects before a full run</h3>
      <p>
        Three sampled images only. This does not validate steps or prove tracking works throughout
        the video.
      </p>
      {frame && (
        <div
          className="object-preview-image"
          style={{ aspectRatio: `${frame.width}/${frame.height}` }}
        >
          <img src={frame.image} alt={`Sampled recording at ${frame.t.toFixed(1)} seconds`} />
          <svg
            viewBox={`0 0 ${frame.width} ${frame.height}`}
            role="img"
            aria-label="Object mask outlines"
          >
            {Object.entries(frame.objects).flatMap(([name, d]) =>
              d
                ? d.contours.map((c, i) => (
                    <polygon
                      key={`${name}-${i}`}
                      points={c.map((p) => p.join(',')).join(' ')}
                      fill="none"
                      stroke="#35d9a0"
                      strokeWidth="2"
                    />
                  ))
                : [],
            )}
          </svg>
        </div>
      )}
      <div className="actions">
        {preview.frames.map((_, i) => (
          <button className="button" key={i} aria-pressed={i === index} onClick={() => setIndex(i)}>
            Preview frame {i + 1}
          </button>
        ))}
      </div>
      <div className="preview-objects">
        {preview.protocol.objects.map((obj) => {
          const observed = preview.objects.find((o) => o.name === obj.name);
          return (
            <label key={obj.name}>
              {obj.name}
              <input
                type="text"
                aria-label={`Description for ${obj.name}`}
                value={prompts[obj.name] ?? obj.sam_prompt}
                maxLength={200}
                disabled={disabled}
                onChange={(e) => onPrompt(obj.name, e.target.value)}
              />
              <small>
                {observed
                  ? `Mask found in ${observed.visible_frames} of ${observed.total_frames} preview frames`
                  : 'No preview measurement'}
              </small>
            </label>
          );
        })}
      </div>
      <p className="field-help">
        Use visible features: color, shape and markings. Refining a description does not change the
        rules; changed descriptions make this run’s protocol unverified.
      </p>
    </section>
  );
}
