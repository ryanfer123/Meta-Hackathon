import type { Run } from '../types';
const flags = new Set([
  'skipped',
  'out_of_order',
  'wrong_object',
  'dwell_exceeded',
  'dwell_too_short',
]);
export function runSummary(run: Run) {
  const flagged = new Set(
    run.events.filter((e) => e.tier === 'rules' && flags.has(e.kind)).map((e) => e.step_id),
  );
  let confirmed = 0,
    unconfirmed = 0,
    findings = 0;
  for (const step of run.protocol.steps) {
    if (flagged.has(step.id)) findings++;
    else if (run.states[step.id] === 'DONE') confirmed++;
    else unconfirmed++;
  }
  return { confirmed, flagged: findings, unconfirmed };
}
