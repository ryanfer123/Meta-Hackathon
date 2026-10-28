# Public app and authenticated processing deployment

App: https://apprentice-meta.onrender.com
API: https://apprentice-api-meta.onrender.com

Source `d29769236f747ac9f08fe7fde14b83fad80b0005` passed backend/frontend CI: https://github.com/ryanfer123/Meta-Hackathon/actions/runs/40554743678.

- Frontend service `srv-dbgcuj29lscs739n0qrg`: static Vite build, public homepage and read-only synthetic sample routes; confirmed Supabase accounts for private library, uploads and live analysis.
- Processing service `srv-dbgeafutlv9c73e2667g`: Render free plan, Singapore, `Dockerfile.api`, Python-only image. Deployment `dep-dbgeagmtlv9c73e26aig` is live.
- Supabase `ntuuztideqsdvuiiohlh`: Auth, owner-scoped tables, private recording/artifact buckets and durable model reservations.
- Both services follow main. A repository commit also redeploys the worker; avoid publishing during an active analysis. Free instances have cold starts and can restart.

The owner explicitly approved storing the Meta API key and separate budget authorization secret as server-side Render environment variables. Neither is a frontend variable or committed file. A deployed JS/CSS check found zero matches for either value. The API image does not build or serve frontend assets, and Uvicorn access logs are disabled to minimize request metadata logging. Supabase tokens travel in headers, never query strings. Provider response bodies and authorization headers are excluded from model-call logs.

`VITE_API_BASE_URL` points at the processing origin. `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` are public browser configuration. Do not put any model, budget or service-role secret in a VITE-prefixed variable. The API has no Supabase service-role key; it uses the authenticated user's JWT for private job/storage operations.

The backend independently verifies a confirmed account with Supabase Auth. Anonymous API requests and an invalid-token upload returned 401 on the live deployment. Private job, report and media access is owner-scoped. A confirmed owner uploaded the labelled synthetic integration clip through the actual browser, Spark compiled its one-step protocol, and the resulting job/archive persisted in Supabase. This is software integration evidence, not a real expert demonstration or accuracy result.

The global reservation ledger caps estimates at $5 per UTC day, $2 per job, 60 Spark calls/day and 800 SAM calls/job. These do not replace provider billing controls or guarantee final charges. Budget authorization/network failures prevent the Meta request. An interrupted worker job becomes an explicit error rather than silently restarting paid work. Completed private archives can restore source/protocol/report files after restart; archive filenames and expanded size are validated.

No GPU/Modal service was started. API-only Spark review is the default. Physical expert A/B, labelled dev/test recordings, and the submission video remain pending.

The synthetic supervision test also finished and persisted an archive. It retained uncertainty rather than completing a step whose tube mask was missing. Private video playback and HTML report requests returned 200; browser chain verification matched the stored root. Physical-procedure evaluation is still pending.

## Optional Baseten advisory tier

The optional open-model tier uses the existing OpenAI-compatible Chat Completions adapter. Baseten's official [quickstart](https://docs.baseten.co/quickstart) and [Model API overview](https://docs.baseten.co/inference/model-apis/overview) verify base URL `https://inference.baseten.co/v1`, endpoint `/chat/completions` and `Authorization: Bearer <Baseten API key>`. Its [vision guide](https://docs.baseten.co/inference/model-apis/vision) documents standard `image_url` content parts. Keep its key in backend-only `GLIMMER_API_KEY`; a Meta Model API key is not a Baseten key.

```env
GLIMMER_BASE_URL=https://inference.baseten.co/v1
GLIMMER_API_KEY=<your Baseten API key>
GLIMMER_MODEL=meta-models/muse-spark-open-1026
GLIMMER_MAX_TOKENS=3000
OPEN_TIER_LABEL=spark-open
```

The hackathon guide supplies the `-1026` alias. Official general Baseten documentation confirms `meta-models/muse-spark-open`, but access to the event-specific alias and this user's image endpoint has not been verified with a paid request. Do not replace the hackathon alias silently. Run the opt-in spike only with explicit `--allow-paid-calls` approval and an image; the existing `glimmer_vision` observation now identifies the configured model and label. No Baseten account, deployment, key or call was created by these changes. This is optional; API-only Spark remains available without an open endpoint.

`GLIMMER_MAX_TOKENS` defaults to 3000. An explicit incomplete/length stop is logged as an error and is not automatically retried. Presentation wrappers such as Markdown fences or leading reasoning are tolerated by extracting the first valid JSON object, but the Pydantic schema remains strict and validation retries remain capped at two after the original answer. Model opinions never complete a rule step or replace missing pixels.

Display labels and metric distributions use `OPEN_TIER_LABEL` (default `glimmer`); Muse Spark Open model IDs automatically use `spark-open` if the default label was left unchanged. The event routing enum remains `glimmer` for schema compatibility, with the configured label used by report/UI display and shadow metadata. A non-loopback endpoint, including Baseten or Modal, counts as cloud egress.

Every attempted shadow opinion is recorded, including escalated Spark opinions and unavailable responses. `shadow_requested` counts completed steps reviewed; `shadow_opinions_requested` counts tier attempts; `shadow_agreement` is agreement across available opinions, including escalations. Disagreement and escalated answers stay advisory; events preserve both tier answers.

Validation now records compile/held-out per-step states and targets repairs only at non-discriminative steps, eligible unflagged counterfactual steps and replay steps not DONE. `repair_history` records attempted and changed step IDs per round. The bounded loop stops when verified, when no failing steps can be identified, or when a round changes nothing. Failure without a targeted repair remains unverified.

The unused WebSocket endpoint was removed. Browser job status uses authenticated HTTP polling.
