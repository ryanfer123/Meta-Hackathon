# Apprentice

**Every step. Accounted for.** A browser workstation that turns expert demonstrations into inspectable physical procedures, then checks later recordings with temporal geometry.

[Live replay](https://apprentice-meta.onrender.com) · [Deployment status](docs/DEPLOYMENT.md) · [Judge review](docs/JUDGE_REVIEW.md) · [Architecture](docs/ARCHITECTURE.md) · [Limitations](docs/LIMITATIONS.md)

**Current evidence:** the public replay uses six original synthetic scenes and a handwritten protocol. It exercises the real Python rule engine, playback, deviations and audit chain. Meta inference, learning from real recordings, Glimmer deployment, real accuracy and model latency remain unverified until API configuration and recordings are supplied. This is not yet a competition-ready scientific result.

## Run locally

Python 3.11–3.14, Node 22.9+, and [uv](https://docs.astral.sh/uv/). No API key needed for replay.

```sh
uv sync --frozen
uv run python scripts/export_samples.py
cd frontend
npm ci
npm run build
cd ..
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. For frontend development use `npm run dev` in `frontend`; it proxies `/api` and `/ws` to port 8000. For static-only replay, `npm run dev` works without Python once bundled samples exist.

Try **Skipped cap**, seek to the event markers, inspect a step's predicate, switch to **Clean procedure**, then **Audit → Verify chain**. Learn exposes the sample protocol and pending validation checks. Nothing is represented as a real model call.

## Live workflow (after configuration)

Copy `.env.example` to `.env` and set `REPLAY_MODE=false`, `MODEL_API_KEY`, and optionally `GLIMMER_BASE_URL`, `GLIMMER_API_KEY`, `GLIMMER_MODEL`. Keys stay server-side. Restart the backend. Install ffmpeg to extract narration, or provide timestamped narration JSON in Learn. Never paste keys into the UI or commit them.

1. Upload expert A in Learn; inspect the Spark-generated protocol.
2. Upload held-out expert B and manually annotated A step boundaries; run all four checks. Optional repair is bounded to 3 rounds and the request budget.
3. Upload the novice recording; inspect masks and decisions in Supervise.
4. Export the HTML report, chain and root. Keep the root separately.
5. Follow [recording and frozen evaluation instructions](docs/RECORDING.md). Real results belong in [eval/results.md](eval/results.md).

The observer currently uses SAM image keyframes at 2 fps, requires distinct object prompts, and refuses ambiguous identity assignments. Count/absence require explicit complete coverage and may remain unknown in live input. Default budgets deliberately reject excessive calls; long recordings with many objects may need a measured budget increase. Live API hosting is intended for a trusted local/private instance; the public site runs static replay only.

## Models propose. Pixels ground. Code decides.

| Component | Role | Current validation |
|---|---|---|
| Muse Spark 1.3 | Propose/repair strict Protocol JSON; advisory escalation | Mocked transport; live pending |
| SAM 3.1 | Text-prompt masks via Responses, official Python parser | Installed parser + malformed/empty fixtures; live pending |
| Muse Voice Transcribe | Narration turn timestamps via `/asr/transcribe` | Documented adapter; live pending |
| Muse Glimmer 30B | Advisory verification + shadow review on every completed step | Routing tested; GPU/vision pending |
| Python predicates/state machine | All completion/deviation decisions | Synthetic and unit checks |

[SAM API](https://dev.meta.ai/docs/sam/overview), [Voice API](https://dev.meta.ai/docs/speech-to-text), and [Glimmer serving](https://dev.meta.ai/docs/muse-glimmer/deploy) were checked on Oct 27, 2026. The BF16 Glimmer path needs about 72 GB serving VRAM; `scripts/modal_glimmer.py` targets A100-80GB and is prepared, not deployed. Modal counts as cloud egress. No air-gap claim is made.

After local configuration, an explicit paid spike can be run:

```sh
uv run python scripts/spike.py --image path/to/frame.jpg --audio path/to/mono.wav --video path/to/short.mp4 --allow-paid-calls
```

It records actual observations and latency/usage under `data/runs/<id>/`; fill [API notes](docs/meta_api_notes.md) from those results. For GPU serving, install/configure Modal and its named secret, then explicitly run `modal deploy scripts/modal_glimmer.py`. Verify the image+text spike before claiming open-weight vision usage.

## Checks

```sh
uv run pytest -q
uv run ruff check backend scripts eval
uv run ruff format --check backend scripts eval
uv run mypy --strict backend/app
cd frontend
npm run build
npm run test:e2e
```

Browser tests require Playwright Chromium (`npx playwright install chromium`) and start their own dev server on port 5174. CI installs it automatically. Unit tests never call live providers. Test count and current CI outcome are visible in the workflow; local checks do not establish live inference.

Evaluation uses exact deviation type + step, ±2 s, maximum one-to-one matching, a frozen test manifest/video hashes, per-type counts and Wilson intervals. Empty data cannot produce a success result. Real performance is **pending**; synthetic regression checks are not a substitute.

## Audit and privacy

The event hash chain covers canonical event data, evidence-image digest and predecessor hash. A separately trusted root is required to detect replacement of the entire chain. It is not tamper-proof and does not authenticate the camera or physical truth. Browser verification checks event/chain/root consistency; checking evidence pixels also requires the original files.

SAM and Spark send frames to Meta; remote Glimmer sends them to its host. Logs count frame transmissions, including retries, and distinguish loopback inference. Real egress %, tier distribution and shadow agreement remain unmeasured in synthetic replay.

## Hackathon scope

Created during the event; see [NEW_WORK](docs/NEW_WORK.md). Indie Developer / Push the Frontier. [Submission preparation](docs/SUBMISSION.md) lists the remaining evidence gates. The concept is designed to support an inspectable demo; a win cannot be inferred from a project brief.

MIT-licensed project source; dependencies and model weights retain their own licenses.
