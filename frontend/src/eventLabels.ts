import type { Event } from './types';

const eventLabels: Record<string, string> = {
  step_started: 'Step started',
  step_completed: 'Step done',
  skipped: 'Step skipped',
  out_of_order: 'Done out of order',
  wrong_object: 'Wrong item used',
  dwell_exceeded: 'Took too long',
  dwell_too_short: 'Done too quickly',
  uncertain: 'Needs a human look',
  shadow_disagreement: 'Second opinion differed',
  escalated: 'Sent for a closer look',
  resolved: 'Review resolved',
};
export const friendlyEventLabel = (kind: string) => eventLabels[kind] ?? kind.replaceAll('_', ' ');
export const checkedBy = (tier: string, openTierLabel = 'glimmer') =>
  tier === 'rules'
    ? 'Rules engine'
    : tier === 'glimmer'
      ? openTierLabel
      : tier === 'spark'
        ? 'Spark'
        : tier;
export function flagReason(event: Event): string {
  const reasons: Record<string, string> = {
    skipped: 'A later step was observed before this step was confirmed.',
    out_of_order: 'This action was observed before an earlier required step was confirmed.',
    wrong_object: 'An action involved a different item from the one this step expected.',
    dwell_exceeded: 'This step stayed active longer than the checklist allows.',
    dwell_too_short: 'This step finished sooner than the checklist allows.',
    uncertain:
      'The visible evidence was not clear enough to confirm this step. A person needs to review it.',
    shadow_disagreement:
      'A second model opinion differed from the other checks. It does not override the rules.',
    escalated: 'The evidence needed a closer model review. That opinion cannot complete a step.',
  };
  return reasons[event.kind] ?? event.detail;
}
