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
