# Apprentice

**Good work. Worth repeating.** A browser workstation that turns expert demonstrations into inspectable physical procedures, then checks later recordings with temporal geometry.

[Live replay](https://apprentice-meta.onrender.com) · [Deployment status](docs/DEPLOYMENT.md) · [Judge review](docs/JUDGE_REVIEW.md) · [Architecture](docs/ARCHITECTURE.md) · [Limitations](docs/LIMITATIONS.md)

**Current evidence:** the public replay uses six original synthetic scenes and a handwritten protocol. It exercises the real Python rule engine, playback, deviations and audit chain. Initial live Spark text/image and SAM image adapter checks passed on an illustrative image. Voice timestamps and native SAM video transport also passed on synthetic fixtures. The authenticated hosted worker compiled a protocol from a synthetic animation and persisted its private archive. Real physical-procedure accuracy and held-out evaluation remain unverified; Glimmer is optional in the API-only configuration. This is not yet a competition-ready scientific result.

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

Open `http://127.0.0.1:8000`. For frontend development use `npm run dev` in `frontend`; it proxies `/api` and `/ws` to port 8000. For a fully static replay, set `VITE_STATIC_REPLAY=true` and run `npm run dev` without Python. Bundled samples require no API keys, Supabase configuration, backend or account. Open `/#/workspace?sample=skipped-cap&view=Supervise` (or `view=Audit` / `view=Learn`).

Try **Skipped cap**, seek to the event markers, inspect a step's predicate, switch to **Clean procedure**, then **Audit → Verify chain**. Learn exposes the sample protocol and pending validation checks. Nothing is represented as a real model call.

## Private cloud workspace

The homepage and six synthetic sample replays are public. Signed-out visitors can play/seek samples, inspect predicates and sample protocols, download sample audits, and verify their chains in the browser. A persistent banner identifies sample mode. Uploading recordings or chains, live Learn/analysis, saving runs, and listing the private run library require a confirmed Supabase account and show sign-in when requested. Signing out clears mounted private run/form state before returning to a bundled sample or the private-route sign-in screen. Sign in to save/reopen/delete run snapshots and upload source recordings to a private library. Supabase provides email/password Auth, Postgres, and private Storage. Recording uploads are staged source material; choose Use in Learn to load them into the compilation, held-out or novice workflow. Analysis jobs and their private output archives persist in Supabase.

For a local cloud-enabled frontend, copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_SUPABASE_URL` plus `VITE_SUPABASE_PUBLISHABLE_KEY`. Only the public client key belongs here. Never put a service role or model key in a `VITE_` variable. Set `VITE_STATIC_REPLAY=true` when serving a static replay without Python. These variables are compiled at build time.

Database setup and authorization tests are in [supabase/README.md](supabase/README.md). Every protocol, run, recording row, and stored file is restricted to its authenticated owner. Snapshot saving/deletion is transactional; private playback URLs expire after 60 seconds.

## Live workflow (after configuration)

Copy `.env.example` to `.env` and set `REPLAY_MODE=false`, `MODEL_API_KEY`, and optionally `GLIMMER_BASE_URL`, `GLIMMER_API_KEY`, `GLIMMER_MODEL`. Keys stay server-side. Restart the backend. Install ffmpeg to extract narration, or provide timestamped narration JSON in Learn. Never paste keys into the UI or commit them.

1. Upload expert A in Learn; inspect the Spark-generated protocol.
2. Upload held-out expert B and manually annotated A step boundaries; run all four checks. Optional repair is bounded to 3 rounds and the request budget.
3. Upload the novice recording; inspect masks and decisions in Supervise.
4. Export the HTML report, chain and root. Keep the root separately.
5. Follow [recording and frozen evaluation instructions](docs/RECORDING.md). Real results belong in [eval/results.md](eval/results.md).

The observer currently uses SAM image keyframes at 2 fps, requires distinct object prompts, and refuses ambiguous identity assignments. Count/absence require explicit complete coverage and may remain unknown in live input. Default budgets deliberately reject excessive calls; long recordings with many objects may need a measured budget increase. The separate API service requires a verified Supabase bearer token and owner-scoped access for private jobs and paid operations. Only health, the six known synthetic sample routes and their run/report/verify/media endpoints are public. Sample data is generated locally without model calls, Supabase writes or budget reservations. Public sample API routes have a best-effort 30 requests per rolling minute per socket IP limit; static bundled assets do not use that API. Set `VITE_API_BASE_URL` to its origin. Tokens are sent in headers, never media URLs. `AUTH_REQUIRED=false` is only for private local development/tests and must not be used on a public service.

Masks are stored losslessly as packed bits, with an 8 MiB process-wide decoded-mask cache. A synthetic 180-frame × 8-object case at 1024×768 stores 141.6 MB of packed masks including byte headers; the regression test also counts instance metadata and cached rasters and stays below 200 MB. Display contours are capped at 256 points per object while predicates and evidence overlays use the exact masks. A noisy 90-second synthetic run's final JSON measured 24,361,428 bytes before and 4,613,268 after the display cap. These are storage checks, not a measured peak-RSS or physical-performance claim.

## Models propose. Pixels ground. Code decides.

| Component | Role | Current validation |
|---|---|---|
| Muse Spark 1.3 | Propose/repair strict Protocol JSON; advisory escalation | Live text/two-image Opinion JSON spike passed; full protocol live validation pending |
| SAM 3.1 | Text-prompt masks via Responses, official Python parser | Live image response parsed; 2 ambiguous candidates; video tracking pending |
| Muse Voice Transcribe | Narration turn timestamps via `/asr/transcribe` | Timestamped Voice response verified on a synthetic spoken test clip; real expert audio pending |
| Muse Spark advisory | API-only review and shadow opinion on every completed step | Rules remain authoritative; routing tested |
| Muse Glimmer 30B (optional) | Alternative open-weight advisory tier | Not deployed; not required by the API-only configuration |
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

## Hosted processing safety

`Dockerfile.api` builds Python only; no model key is a frontend build input. The processing service uses a server-side Meta key, the signed-in user's JWT for owner-scoped storage, and a separate server-only key authorizing durable budget reservations. It does not use a Supabase service-role key. Database reservations serialize concurrent calls with conservative limits of $2 per job and $5 per UTC day, 60 Spark calls/day and 800 SAM calls/job. These are estimates, not a billing guarantee; provider billing controls remain separate. Unknown/denied budget authorization fails before contacting Meta.

Completed job archives survive worker restarts. A restart during processing fails the interrupted job explicitly rather than silently restarting paid work. The free worker has cold starts and resource limits; it is a hackathon preview, not a production queue. Keep recordings short, at most 50 MB, and retain source copies.

## Acknowledgments

The Learn workspace links to Science Buddies' **How to Make a Serial Dilution** as an external reference. See [acknowledgment.md](acknowledgment.md) for credit, original sources and reuse status. The video is not bundled or represented as a completed Apprentice analysis.

## Detailed native-video spike (T3 step 1)

The detailed spike makes one native-video SAM request and skips the other modality checks. Run it yourself only when ready to authorize that paid call:

```sh
uv run python scripts/spike.py --native-video-detail \
  --video path/to/short-h264.mp4 --prompt 'tube' --allow-paid-calls
```

Use an MP4 no longer than 30 seconds and no larger than 10 MiB, ideally with two visible matching props to inspect tracking identities. Review the printed `data/runs/spike-*/observations.json` and share its `native_video_detail` block before enabling native tracking. Source average FPS, reported processed-frame averages and sparse emitted frame references are reported separately. Production remains image-keyframe SAM; T3 steps 2–7 require these real observations. No new paid call has been run.


## Batch recording workflow (T4)

Prepare the labels before opening model predictions. Use a validated protocol from Learn and distinct dev/test recordings. The manifest helper reads filenames only and creates empty event lists; inspect every `source: "real"` entry and label the footage manually. An empty list means a reviewed clean recording only after you have actually watched it.

```sh
uv run python scripts/make_manifest.py --videos eval/runs/dev --predictions data/batch/dev --split dev --out eval/labels.json
uv run python scripts/make_manifest.py --videos eval/runs/test --predictions data/batch/test --split test --out eval/labels.json
```

Fill labels, tune on dev only and freeze the test manifest with the existing evaluator before running the test set. Never use model predictions as ground truth.

For trusted local batch analysis configure `REPLAY_MODE=false`, `CLOUD_JOBS=false`, and the server-side model key in ignored local environment configuration. Use API-only mode (leave `GLIMMER_BASE_URL` empty) when requesting a cumulative cost cap:

```sh
uv run python scripts/run_batch.py --protocol data/jobs/PROTOCOL_ID/protocol.json --videos eval/runs/dev --out data/batch/dev --split dev --max-cost-usd 2 --allow-paid-calls
uv run python scripts/run_batch.py --protocol data/jobs/PROTOCOL_ID/protocol.json --videos eval/runs/test --out data/batch/test --split test --max-cost-usd 2 --allow-paid-calls
```

Each video produces `<stem>.prediction.json` and `<stem>/report.html`, `chain.json`, `root.txt`. The reusable `run_recording` function is the same analysis pipeline used by the API. Existing ready predictions are skipped only when source SHA-256, protocol and split match. A changed video becomes a new attempt. Output folders bind to one protocol, split and local ledger; choose a new folder when these change. Keep generated outputs and recordings out of Git.

The terminal table reports status, event count, cloud frame transmissions, estimated cost and elapsed seconds. Unknown costs are printed as `unknown`. Errors or exhausted budgets return exit code 2. Batch use is opt-in even for an idempotent rerun; without `--allow-paid-calls`, the runner exits before loading configuration or constructing model clients.
