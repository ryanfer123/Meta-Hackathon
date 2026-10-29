# Apprentice

**Show it once. Check each step.** Turn an example video into a checklist, then compare another recording to find missed steps and actions in the wrong order. Select an alert to see its reason and evidence frame.

[Try the public sample](https://apprentice-meta.onrender.com/#/workspace?sample=skipped-cap&view=Supervise) · [Recording guide](docs/RECORDING.md) · [Results](eval/results.md) · [Limitations](docs/LIMITATIONS.md)

[![Animated sample: the cap step is flagged beside its playback](frontend/public/images/product-supervise.png)](https://apprentice-meta.onrender.com/#/workspace?sample=skipped-cap&view=Supervise)

**What you can try now:** six animated samples, step-by-step playback, event inspection and report verification. No account or API key needed. Sign in to upload and save your own recordings. Samples are synthetic; accuracy on physical procedures is **not measured yet**.

**Three-minute demo video:** pending real procedure footage. No submission video is published yet.

## How it works

1. **Learn:** upload a narrated example. Review the suggested checklist and confirm the proposed narration-based step timings. Test it against a second expert take and deliberate missing/reordered steps.
2. **Supervise:** check another recording. SAM supplies object masks; Python rules decide whether a step happened. A model opinion cannot mark a step complete. A blocked view stays uncertain.
3. **Audit:** review flagged moments and download the report. Keep the exported root separately to detect later event-log changes; this does not authenticate the camera or prove physical correctness.

The tabletop demonstration checks visible handling, not liquid concentration, volume, sterility or cap tightness.

## Run locally

Requires Python 3.11–3.14, Node 22.9+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --frozen
uv run python scripts/export_samples.py
cd frontend
npm ci
npm run build
cd ..
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. For a frontend-only replay, set `VITE_STATIC_REPLAY=true` and run `npm run dev` in `frontend`; no backend or credentials are needed. Try **Skipped cap**, seek to the alert, then open **Audit → Verify chain**.

## Private cloud workspace

Only the homepage and six bundled samples are public. Uploads, paid processing, saving and the run library require a confirmed account. Supabase restricts rows and files to their owner. Private media uses authenticated fetching; credentials are never placed in URLs.

Set up the backend from `.env.example`; set `REPLAY_MODE=false` and a server-side `MODEL_API_KEY` for paid work. The optional Baseten tier uses `meta-models/muse-spark-open-1026`. Never put a model key or service-role key in a frontend `VITE_` variable. Cloud SAM and model requests transmit selected images to their providers; this is not an offline pipeline.

**Tracking defaults to image mode.** Native video remains experimental. A completed native response with zero masks triggers a logged, separately budgeted image fallback; incomplete or ambiguous geometry stays unknown. Native success on a short diagnostic clip does not establish procedure accuracy.

The image-mode allowance is deliberately sized for two 90-second expert takes: 3,000 image calls and an $8/job reservation cap; local and hosted daily caps are $10. Experimental native mode allows 6,000 billed frames. Requests refuse before exceeding configured reservations; these estimates are not provider billing guarantees. See `.env.example` before enabling live processing.

## Checks and current priority

```sh
uv run pytest -q
uv run ruff check backend scripts eval
uv run ruff format --check backend scripts eval
uv run mypy --strict backend/app
cd frontend
npm run build
npm run test:e2e
```

Tests use mocked providers and synthetic masks. Paid probes require explicit `--allow-paid-calls`. Physical expert A/B recordings, a labelled dev/test set and a frozen-test report remain the next evidence gates. Features are frozen apart from fixes needed to collect and validate that footage.

<details>
<summary>Developer reference</summary>

[Architecture](docs/ARCHITECTURE.md) · [API observations](docs/meta_api_notes.md) · [Deployment](docs/DEPLOYMENT.md) · [QA](docs/QA.md) · [Database setup and migrations](supabase/README.md) · [New work](docs/NEW_WORK.md) · [Submission](docs/SUBMISSION.md)

</details>

MIT-licensed project source. Third-party footage, model weights and dependencies retain their own terms; see [acknowledgments](acknowledgment.md).
