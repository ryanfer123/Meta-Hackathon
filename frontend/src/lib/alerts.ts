import { isAlert, type Event, type Run } from '../types';

const severity = [
  'wrong_object',
  'skipped',
  'out_of_order',
  'dwell_too_short',
  'dwell_exceeded',
  'uncertain',
  'shadow_disagreement',
  'escalated',
];

/** Select a headline without changing the chronological event stream. */
export function headlineAlert(run: Run): Event | undefined {
  const focus = run.focus;
  if (focus) {
    const match = run.events.find(
      (event) =>
        isAlert(event.kind) &&
        event.kind === focus.kind &&
        event.t === focus.t &&
        event.step_id === focus.step_id,
    );
    if (match) return match;
  }
  const alerts = run.events.filter((event) => isAlert(event.kind));
  const earliestStep = run.protocol.steps.find((step) =>
    alerts.some((event) => event.step_id === step.id),
  );
  // Unassigned alerts remain eligible when no protocol step is affected.
  const candidates = earliestStep
    ? alerts.filter((event) => event.step_id === earliestStep.id)
    : alerts;
  const rank = (event: Event) => {
    const index = severity.indexOf(event.kind);
    return index < 0 ? severity.length : index;
  };
  return [...candidates].sort((a, b) => rank(a) - rank(b) || a.t - b.t)[0];
}

/** Earlier observations on this step explain context, not proven physical causation. */
export function earlierAlertContext(run: Run, selected: Event): string {
  if (!selected.step_id) return '';
  const earlier = run.events.filter(
    (event) => event.step_id === selected.step_id && event.t < selected.t && isAlert(event.kind),
  );
  const descriptions: Record<string, string> = {
    dwell_exceeded: 'It also stayed active longer than allowed first.',
    uncertain: 'The evidence for this step was unclear earlier.',
    wrong_object: 'An earlier action on this step involved the wrong item.',
    dwell_too_short: 'This step was also observed finishing too quickly earlier.',
    out_of_order: 'This step was also observed out of order earlier.',
    skipped: 'This step had already been flagged as skipped.',
    shadow_disagreement: 'A second opinion on this step differed earlier.',
    escalated: 'This step was sent for a closer look earlier.',
  };
  return [...new Set(earlier.map((event) => descriptions[event.kind]).filter(Boolean))].join(' ');
}
