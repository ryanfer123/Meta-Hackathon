# Verification notes

## Tracking review and evidence probes - October 29, 2026

Full checks cover Python tests, Ruff check/format, strict mypy, the production build and desktop/mobile Playwright. Provider requests are never part of tests. The suite covers zero-mask fallback, private raw-response retention, image/video cost refusal, confirmed narration timings and bounded recovery. Synthetic samples remain explicitly labelled; physical procedure evaluation is pending.

Three specifically authorized diagnostic requests reserved $0.0625 total against a shared $0.10 local cap: synthetic SAM image control (zero masks), photographic SAM video control (50 masks/12 frames) and Baseten image/text (valid JSON). Exact observations and limits are in [API notes](meta_api_notes.md); local full bodies are ignored private files. Historical empty native bodies cannot be reconstructed from their old extracted-text fixtures.

The photographed source is OpenCV's public sample, used only as a diagnostic. It is not Apprentice procedure footage and is not offered as a competition result. No frozen-test metric exists yet. Next work is consented expert A/B and labelled dev/test footage; feature work must not substitute for that evidence.

Commands are in the README. Commit history retains earlier QA notes and their scope.


## T6 first-visit UX - October 30, 2026

Home → selected, paused alert works in two clicks with `/api` blocked. Desktop/mobile checks cover aliases, guided Teach, confirmed video timings, stale-response rejection, read-only examples, actual-count model chips, unknown verification failures, clipboard export and the unified private list. Product previews were recaptured from current animated views; no model accuracy is implied. 275 Python tests and 118 desktop/mobile browser checks passed, along with lint/format, strict typing and the production build. T7 remains pending consented footage.


## T6.1 headline alerts - October 30, 2026

Scenario metadata selects each example’s headline finding without changing its chronological events or integrity root. Skipped cap opens paused on “Step skipped” at 00:17 on Home and the landing comparison; the earlier same-step time warning stays in the timeline and reason panel. Shared-helper tests cover all six samples, stale metadata, step order and severity; desktop/mobile first-visit checks run with `/api` blocked. 281 Python tests and 136 desktop/mobile browser checks passed, plus lint/format, strict typing and the build. T7 remains pending a consented real run.


## Private real-video website check — October 31, 2026

Signed-in Teach → Check → My runs → Results was exercised with a licensed rope clip. Real playback/overlays/seeking, actual SAM and Spark Open usage chips, browser chain verification and HTML download worked. The browser poll expired before the slow image job completed; My runs recovered the result. Zero of five unverified steps completed, despite advisory model suggestions. Native single-concept tracking returned masks; a full native batch stopped at its advisory cap. No accuracy result or public real sample is claimed; details and reservations are in the API notes.

## Evidence-specific uncertainty and advisory presentation — October 31, 2026

Offline tests cover missing evidence, blocked predecessors, vacuous completion conditions, step-only prompts, timestamped measurements, bounded temporal frame selection and escaped/collapsed HTML opinions. Desktop/mobile replay tests verify that model prose starts collapsed, opens on request and is labelled advisory. Historical hashes and decisions are retained; no new provider accuracy claim or paid probe is included.

## Bounded image concurrency and progress — October 31, 2026

Mocked transports compare serial/parallel masks and ordering, bound admitted work, retain per-request logs and refuse excess reservations before transport. Local and mocked hosted status tests check private progress and peer refusal. Desktop/mobile tests cover measured progress, stage changes, stale estimates and replacement of inactive form controls. The small paid one-frame control is separately documented in API notes; it is not an end-to-end benchmark.

## Recording-first presentation — October 31, 2026

The landing page and normal workspace lead to signed-in teaching/checking, never automatically loading sample data. Results stays empty until a run is selected. Existing explicit sample deep links retain static playback, honest provenance and integrity checks. Updated browser coverage checks no sample requests in ordinary flows, auth at upload entry, actual-run library reopening, responsive image loading and reduced motion. Product captures are generated from current empty workspace views with mocked authentication/configuration, not simulated analysis results; no paid calls are made. Explicit `CAPTURE_PRODUCT=1` capture refreshes documentation assets.

The final pass also fixed a concurrent-error reporting race: a provider/parser failure is no longer hidden by a sibling budget refusal. Both thread orders are tested, with budget reservations retained. Final local checks:302 Python tests,142 desktop/mobile browser checks (two opt-in capture cases skipped), Ruff check/format, strict mypy and production build. Mobile homepage inspection found no horizontal overflow or runtime errors. No paid calls were made.

## Beige, dark mode and motion — November 1, 2026

Added persistent beige/near-black themes, keyboard-accessible toggles, staggered hero text, once-only scroll reveals, bounded fine-pointer tilt, reading progress and shared sidebar selection transitions. Focused desktop/mobile checks cover reload/auth persistence, input preservation, readable dark controls, pointer reset and reduced-motion suppression; captures wait for settled page opacity. Product previews were recaptured in both themes from empty workspace views. No model calls or backend decisions changed.

Theme/motion verification:302 Python tests,149 desktop/mobile browser checks,three intentional skips (two captures and fine-pointer tilt on touch), lint/format, strict typing and build passed. The existing Motion dependency is used; no runtime dependencies or paid calls were added.

## Per-analysis faster tracking — November 1, 2026

Added a keyboard-accessible, per-job native-video preview choice to Check and validation; preserved default image mode and all caps. Verified both POST fields, omitted/invalid values, auth rejection, unchanged settings, completed-empty negative caching, bounded decoding reuse and geometry-key invalidation, bit-identical disk reconstruction and invalid-cache refusal offline. Browser plugin not available; regular Playwright verified desktop/mobile checkbox state, accessible help, multipart submission and no horizontal overflow. Local checks:318 Python tests,151 browser checks (three intentional skips), Ruff check/format, strict mypy and production build passed. Mobile screenshot: `/tmp/apprentice-tracking-choice-mobile.png`. Real-clip tracking diagnostic is documented separately in API notes; these UI checks make no quality claim.

Private tracking control:seven native calls, $0.0742 reserved; original cold tracking213.311s and cached-text tracking162.741s. Updated offline geometry-cache fill81.018s, warm replay0.672s, matching packed geometry digest and zero permitted network requests. These are tracking-only timings on one short clip, not hosted whole-job latency or measured accuracy.
