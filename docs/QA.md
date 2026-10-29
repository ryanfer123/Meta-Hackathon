# Verification notes

## Tracking review and evidence probes - October 29, 2026

Full checks cover Python tests, Ruff check/format, strict mypy, the production build and desktop/mobile Playwright. Provider requests are never part of tests. The suite covers zero-mask fallback, private raw-response retention, image/video cost refusal, confirmed narration timings and bounded recovery. Synthetic samples remain explicitly labelled; physical procedure evaluation is pending.

Three specifically authorized diagnostic requests reserved $0.0625 total against a shared $0.10 local cap: synthetic SAM image control (zero masks), photographic SAM video control (50 masks/12 frames) and Baseten image/text (valid JSON). Exact observations and limits are in [API notes](meta_api_notes.md); local full bodies are ignored private files. Historical empty native bodies cannot be reconstructed from their old extracted-text fixtures.

The photographed source is OpenCV's public sample, used only as a diagnostic. It is not Apprentice procedure footage and is not offered as a competition result. No frozen-test metric exists yet. Next work is consented expert A/B and labelled dev/test footage; feature work must not substitute for that evidence.

Commands are in the README. Commit history retains earlier QA notes and their scope.
