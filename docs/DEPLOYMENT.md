# Public app and authenticated processing deployment

App: https://apprentice-meta.onrender.com
API: https://apprentice-api-meta.onrender.com

Source `d29769236f747ac9f08fe7fde14b83fad80b0005` passed backend/frontend CI: https://github.com/ryanfer123/Meta-Hackathon/actions/runs/40554743678.

- Frontend service `srv-dbgcuj29lscs739n0qrg`: static Vite build, public homepage, mandatory confirmed Supabase account for workspace routes.
- Processing service `srv-dbgeafutlv9c73e2667g`: Render free plan, Singapore, `Dockerfile.api`, Python-only image. Deployment `dep-dbgeagmtlv9c73e26aig` is live.
- Supabase `ntuuztideqsdvuiiohlh`: Auth, owner-scoped tables, private recording/artifact buckets and durable model reservations.
- Both services follow main. A repository commit also redeploys the worker; avoid publishing during an active analysis. Free instances have cold starts and can restart.

The owner explicitly approved storing the Meta API key and separate budget authorization secret as server-side Render environment variables. Neither is a frontend variable or committed file. A deployed JS/CSS check found zero matches for either value. The API image does not build or serve frontend assets, and Uvicorn access logs are disabled to minimize request metadata logging. Supabase tokens travel in headers, never query strings. Provider response bodies and authorization headers are excluded from model-call logs.

`VITE_API_BASE_URL` points at the processing origin. `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` are public browser configuration. Do not put any model, budget or service-role secret in a VITE-prefixed variable. The API has no Supabase service-role key; it uses the authenticated user's JWT for private job/storage operations.

The backend independently verifies a confirmed account with Supabase Auth. Anonymous API requests and an invalid-token upload returned 401 on the live deployment. Private job, report and media access is owner-scoped. A confirmed owner uploaded the labelled synthetic integration clip through the actual browser, Spark compiled its one-step protocol, and the resulting job/archive persisted in Supabase. This is software integration evidence, not a real expert demonstration or accuracy result.

The global reservation ledger caps estimates at $5 per UTC day, $2 per job, 60 Spark calls/day and 800 SAM calls/job. These do not replace provider billing controls or guarantee final charges. Budget authorization/network failures prevent the Meta request. An interrupted worker job becomes an explicit error rather than silently restarting paid work. Completed private archives can restore source/protocol/report files after restart; archive filenames and expanded size are validated.

No GPU/Modal service was started. API-only Spark review is the default. Physical expert A/B, labelled dev/test recordings, and the submission video remain pending.

The synthetic supervision test also finished and persisted an archive. It retained uncertainty rather than completing a step whose tube mask was missing. Private video playback and HTML report requests returned 200; browser chain verification matched the stored root. Physical-procedure evaluation is still pending.
