import type { Event } from './types';

export function readableDetail(event: Event): string {
  if (event.tier !== 'rules') return 'Model opinion only. Rules remain unchanged.';
  return event.detail.replace(
    'Recording ended before completion.',
    'Could not confirm this step before the recording ended.',
  );
}

export function EventDetail({ event }: { event: Event }) {
  if (event.tier === 'rules') return <>{readableDetail(event)}</>;
  return (
    <>
      <span>{readableDetail(event)}</span>
      <details>
        <summary>Read model opinion</summary>
        <p>{event.detail}</p>
      </details>
    </>
  );
}
