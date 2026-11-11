# Architecture

This describes the post-hackathon development branch. The frozen event snapshot is tagged `hackathon-pre-nov4`; new branch features are not automatically deployed to the main-branch site.

## Boundaries

React calls a Python/FastAPI API. Confirmed Supabase accounts protect uploads, processing, saved work, reports and media. The backend verifies tokens and ownership independently; Supabase RLS scopes records and private storage to the owner. Model keys stay on the backend. Legacy synthetic deep links remain isolated, explicitly labelled compatibility examples.

**Models propose; pixels ground; deterministic code decides.** Protocols and opinions must pass strict Pydantic validation. Only predicates and the temporal state machine complete steps. Missing masks, ambiguous identities and occlusion remain unknown. A model opinion never overrides a rule verdict. Visible geometry does not establish liquid volume, concentration, sterility or cap tightness.

## Pipeline

1. **Teach:** sample the selected expert video, transcribe narration or use its supplied description, and ask Spark for a protocol. Every step needs an observable change. Narration supplies timing suggestions; a person must review the actual start/end ranges.
2. **Validate:** replay expert A and an independent expert B, check discriminative predicates and run eligible cut/swap controls. Repair only failing steps, with bounded rounds. Verification requires all four checks; replaying A alone is not generalization evidence.
3. **Preview:** optionally check three images from the new recording. Display the returned mask contours and per-object mask availability. Users can revise descriptions for the existing objects; doing so clears protocol verification. Preview output is not a completed procedure run. Continuing reuses the upload and job budget.
4. **Check:** ground objects, replay rules, allow one bounded recovery re-query, and obtain advisory/shadow opinions. Store events, evidence and an HTML report. Counts distinguish rule-confirmed, rule-flagged and unconfirmed steps; uncertainty is not automatically a mistake.

## Geometry and provider adapters

`Detection` snapshots masks as immutable packed bits plus shape. Lazy read-only rasters share an 8 MiB LRU; area/centroid caches retain only exact scalars. Predicates use masks, never simplified display contours. New teaching protocols retain their actual evidence resolution, normally up to 512 px; legacy 1024-px coordinate systems remain supported.

Image SAM uses bounded request batches. Native SAM prepares a 4 fps, H.264, at-most-640-px clip once per distinct prompt. Source frame references and persistent IDs are parsed conservatively; identities are not reconstructed by guessing after ambiguity. Missing confidence stays 0.5, not 1.0. A completed zero-mask concept or documented size rejection triggers a logged, separately budgeted image fallback. Neither path guarantees all objects will be found.

`TrackingProvider` returns normalized `FrameState` geometry; `OpinionProvider` returns a validated advisory `Opinion`. The pipeline accepts injected adapters without changing predicates or auditing. The existing Meta adapter and configurable OpenAI-compatible opinion endpoint remain the actual integrations. An alternate in-memory tracker is tested; no additional local model or alternative segmentation service is claimed as deployed. Provider identity participates in checkpoint reuse.

The installed SAM codec is compiled with mypyc in the Docker builder. Source/license remain present; pixel/error parity is checked. The runtime needs no compiler or build dependencies. This is an implementation optimization, not a hosted turnaround guarantee.

## Explicit trimming

The original upload is retained. An optional selection is validated against its actual duration before admission or paid processing. FFmpeg derives that section; encoding has a time cost and does not reduce the original upload's byte size. A small per-input derived cache is pruned independently of originals. Source hash, selected interval and source duration are recorded.

Rules process the selected timeline. Exported run events/frames map back to the original recording's timestamps, and the player restricts its timeline to the checked section. Teaching timing suggestions also use original timestamps; validation converts confirmed source ranges to the selected expert section. Sampling remains 2 fps, so timestamps are not sub-frame physical measurements. Model narrative timestamps can remain relative to the selected section and are labelled accordingly.

## Checkpoints and restarts

New jobs archive originals plus a resume manifest before paid work. Completed narration/compilation and whole-video tracking stages are saved. Tracking checkpoints retain exact packed masks, confidence, absence/unknown state, interactions and source/protocol/mode fingerprints. Array headers and expanded bytes are bounded before NumPy allocates data; no pickle loading is permitted. Evidence paths are rebound to sampled frames after restoration.

My runs offers an explicit resume action. It restores saved inputs and call logs and uses the same budget identity. Completed tracking stages avoid provider calls. An interrupted stage can still lose progress and repeat calls, including advisory opinions in an unfinished review stage. There is no automatic paid retry or exactly-once claim. Saved call logs may omit work lost before the last checkpoint; the durable cloud reservation ledger remains authoritative for refusal limits.

Cloud archives are built on disk and uploaded in 64 KiB chunks. Source footage is capped at 90 MiB combined per cloud job, subject to the configured per-file cap. The final archive cap is 110 MiB: the difference is headroom, not guaranteed capacity for every checkpoint/report. Restores check allowed names, duplicate entries, expanded size and CRCs before installing staged files. HTTP download still buffers a response; this is not a fully streaming download or crash-atomic multi-file restore.

## Free-tier limits and costs

One analysis runs at a time. Busy submissions get a retryable response before paid work. Teaching and native Check accept sections up to five minutes; image tracking remains capped at 90 seconds. Long-job preflight bounds packed masks, processed frames and base reservations; both expert videos share the validation memory calculation.

Every model attempt reserves before requesting. Local reservations use transactional SQLite. Hosted reservations lock a private Supabase ledger shared across owners/models. Per-run/day/frame limits remain, and the hosted calendar-month reservation ceiling is $150. Signed-in clients cannot raise it. Reservations/estimated usage are not provider invoices and cannot govern keys used elsewhere. Meta's provider spend-limit setting is an alert, not a hard stop.

Free services may sleep or restart. Durable snapshots help recover saved stages but cannot promise uninterrupted processing. More credits do not add CPU or RAM.

## Reports and evaluation

Events and evidence digests form a hash chain. Detecting a rewritten chain requires a separately trusted root. Summaries, model opinions and metadata do not authenticate the camera or prove physical correctness.

The blind labelling tool reads local recordings and does not load predictions. Pilot mode requires 6–8 independent evaluation recordings (at least two dev/four test), confirmed labels, excluded expert reference hashes, and a frozen protocol/manifest/video set. It reports per-type counts and uncertainty; the larger six-dev/six-test mode is retained. No independent footage or actual user trial has been supplied, so real accuracy and user feedback remain unmeasured. See [the pilot guide](PILOT.md).
