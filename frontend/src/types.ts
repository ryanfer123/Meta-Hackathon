export type Detection = {
  x: number;
  y: number;
  w: number;
  h: number;
  score: number;
  class: string;
  contours: number[][][];
};
export type Frame = {
  t: number;
  width: number;
  height: number;
  objects: Record<string, Detection | null>;
};
export type Predicate = { op: string; [key: string]: string | number };
export type Step = {
  id: string;
  title: string;
  narration_hint: string;
  pre: Predicate[];
  action: Predicate[];
  post: Predicate[];
  group: string | null;
  min_dwell_s: number;
  max_dwell_s: number;
};
export type Protocol = {
  name: string;
  steps: Step[];
  objects: { name: string; sam_prompt: string; class: string }[];
  verified: boolean;
};
export type Event = {
  t: number;
  step_id: string | null;
  kind: string;
  tier: string;
  confidence: number;
  detail: string;
  evidence_frame: string | null;
};
export type ChainEntry = {
  event: Event;
  evidence_sha256: string | null;
  prev_hash: string;
  hash: string;
  canonical_entry: string;
};
export type Validation = {
  checks: Record<string, boolean | null>;
  verified: boolean;
  repair_rounds: number;
  scope: string;
};
export type Run = {
  id: string;
  name: string;
  provenance: string;
  protocol: Protocol;
  frames: Frame[];
  events: Event[];
  states: Record<string, string>;
  duration: number;
  chain: ChainEntry[];
  chain_root: string;
  validation?: Validation;
  metrics: {
    model_calls: number;
    shadow_agreement: number | null;
    egress_percent: number | null;
    latency_ms?: number | null;
    note: string;
    shadow_available?: number;
    shadow_requested?: number;
  };
};
export type Health = {
  replay_mode: boolean;
  live_configured: boolean;
  glimmer_configured: boolean;
};
export type View = 'Learn' | 'Supervise' | 'Audit';
export const scenarios = [
  ['skipped-cap', 'Skipped cap'],
  ['clean', 'Clean procedure'],
  ['wrong-tube', 'Wrong tube'],
  ['swapped-order', 'Swapped order'],
  ['slow-action', 'Excessive dwell'],
  ['occlusion', 'Partial occlusion'],
];
export const timecode = (t: number) =>
  `${Math.floor(t / 60)
    .toString()
    .padStart(2, '0')}:${Math.floor(t % 60)
    .toString()
    .padStart(2, '0')}`;
export const isAlert = (kind: string) =>
  !['step_started', 'step_completed', 'resolved'].includes(kind);
export const label = (kind: string) => kind.replaceAll('_', ' ');
