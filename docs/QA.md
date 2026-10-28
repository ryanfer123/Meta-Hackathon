## T4 batch workflow - 2026-10-28

- Isolated T4 checkout passed 143 Python tests, 42 desktop/mobile browser checks, Ruff check/format, strict mypy and production build.
- Mocked generated-video tests cover the shared API/CLI pipeline, SHA/protocol/split-aware skipping, audit artifacts, evaluator acceptance, pre-request cumulative budget stops, failed-call reservations and advisory-budget refusals.
- Test-only generated manifests use source=real solely to exercise the evaluator contract; no physical results or batch throughput were measured. No paid calls ran.

## T3 detailed native-video spike preparation - 2026-10-28

- Isolated T3-step-1 checkout passed 133 Python tests, 42 desktop/mobile browser checks, Ruff check/format, strict mypy and production build.
- Thirteen new mocked checks cover explicit sparse frame references, mask-ID recurrence, incomplete/diagnostic unknown evidence, missing confidence/usage, local metadata and limits, single-request behavior, and the explicit paid-call gate.
- No paid call ran. Native tracking, frame-based budget changes and T3 acceptance on real footage remain pending user-run observations.

## T2 compact mask storage - 2026-10-28

- Isolated T2 checkout passed 120 Python tests, 42 desktop/mobile browser checks, Ruff check/format across backend/scripts/eval, strict mypy and the production build.
- All six synthetic sample exports remain exactly equal to the bundled baseline JSON. Packed-mask tests cover non-byte-aligned/empty/None masks, source-array independence, read-only lazy views, cache eviction, HSV fallback and saved evidence overlays.
- A 180 × 8 × 1024×768 memory regression remains below 200 MB after every mask is decoded; internal strong decoded cache is capped at 8 MiB. This is stored memory, not peak worker RSS.
- Seeded noisy 90-second synthetic final run JSON measured 24,361,428 bytes before and 4,613,268 bytes after the 256-point/object display contour cap. Predicate outputs and exact stored pixels are unchanged.
- No paid calls, real recordings or physical-performance claims were added.

## T1 public synthetic replay - 2026-10-28

- Synthetic Supervise, Audit and sample-protocol Learn are public on explicit sample routes. Private root/library/unknown routes remain gated. Live uploads and saved state still require sign-in.
- 42 desktop/mobile Playwright checks passed, including all six samples with API/cloud requests blocked, chain verification, sign-in prompts and clearing private form state on sign-out.
- 104 Python tests passed, including public reads in cloud-job mode without Auth, Meta, cloud storage or budget calls; known-sample allowlisting, private IDs, rate-limit recovery, spoofed forwarded headers and bounded limiter storage.
- Historical mandatory-login and anonymous-sample-401 observations below describe earlier commits and are superseded by T1.

## Motion refinement - 2026-10-28

- Added Motion for React (formerly Framer Motion): staggered hero entrance, one-time viewport reveals, comparison fades, workspace entrances, dialog entrances and notification exits.
- Motion features load in a separate chunk. System reduced-motion preferences disable positional transitions; Learn stays mounted across navigation.
- Verified desktop and mobile screenshots, including intermediate scroll states: no browser errors or horizontal page overflow.
- Validation: 34 desktop/mobile Playwright checks (including reveal persistence and reduced motion), 93 Python tests, Ruff check/format, strict mypy and production build passed. Vite still reports its advisory for the main JavaScript chunk exceeding 500 kB.
- No model calls, credentials, database policies or authentication gates changed.

# Current verification: authenticated API-only processing

- 93 Python checks passed; Ruff, formatting, strict mypy (28 app modules), and production frontend build pass.
- 30 desktop/mobile checks passed locally and against Render: mandatory login, signup confirmation state, invalid/persisted-session rejection, sign-out, intended route retention, replay, library, upload metadata, audits and exports. Browser cloud writes use mocks; the additional live browser compile used the owner's actual confirmed account.
- Real signup/email confirmation succeeded according to the owner; Supabase independently showed one confirmed account. A separate clean browser context displayed the login gate and no workspace controls. No guest continuation exists.
- Live API returned 200 health with authentication/cloud jobs enabled and 401 for anonymous samples and an invalid-token upload.
- The real authenticated browser uploaded the labelled synthetic animation and received a Spark-compiled one-step protocol. Job `f23b6e9873bb4c8ea9365536ddbf9caa` became ready with a private archive in Supabase. It remains unverified; no real expert or held-out results are claimed.
- Hosted supervision job `a977e63c1a084a228612edcb2afd3289` completed and persisted its private archive: 16 frames, 48 SAM image calls and one Spark advisory call. The step remained ACTIVE/uncertain because the synthetic tube was not consistently detected; there was no completion and therefore no completed-step shadow sample. This is an integration check with an honest uncertain outcome, not a passing physical procedure or accuracy evaluation.
- Reopening that job from the private library loaded an 8-second authenticated blob video (`readyState=4`). Media and report requests returned HTTP 200 from the API. The audit chain matched its root, and the browser reported no console errors/warnings. Session tokens were not placed in media URLs. The actual Save run action also succeeded; Supabase confirmed one saved snapshot for this integration run.
- Voice API returned one timestamped turn for non-empty synthetic computer-spoken audio. Native SAM video transport completed for the 80-frame synthetic animation; the production observer still uses image keyframes.
- Live SQL checked owner job isolation, wrong-server-key rejection, run budget limits and private ledger denial, all in rolled-back fixtures. The reservation RPC's SECURITY DEFINER warning is intentional and documented in `supabase/README.md`; its server key is never exposed to browser clients. Private ledger tables have deny-all client RLS.
- Both GitHub jobs passed for source d297692: https://github.com/ryanfer123/Meta-Hackathon/actions/runs/40554743678. Render API deployment dep-dbgeagmtlv9c73e26aig is live.
- Secret matching found no Meta key in tracked source or the frontend build, and no Meta/budget secret in the deployed entry JS/CSS assets. The model key is a backend runtime environment variable, separately approved by the owner.

The browser connector rejected file upload paths outside its configured roots. Native macOS file-picker actions loaded the same synthetic test file; it was never substituted for real footage. Desktop/mobile login captures are local `/tmp/apprentice-auth-desktop.png` and `/tmp/apprentice-auth-mobile.png`.

## Previous release evidence (historical)

# Current verification: homepage and Supabase revision

- Python: 82 tests; Ruff, formatting and strict mypy pass. Frontend production build passes.
- Playwright: 24 desktop/mobile checks cover homepage comparison, image loading, account error handling, saved-run reopen/deletion, private upload metadata, all six replays, Learn form retention, audits and exports. Cloud HTTP is mocked in browser tests; authorization SQL is live.
- Responsive homepage checked at 1440, 768 and 390 px. Four raster images load, no horizontal document overflow, headings fit within two lines. Corrected tablet wrapping and contrast; design inspector reports zero failures. See `FRONTEND_DIRECTION.md` for the render critique and explicit image/footage limits.
- The comparison switches between the actual clean/skipped fixture outputs and opens the selected run. The workflow images are captures of the real interface, not invented model results. Local screenshot artifacts live outside source control under `/tmp/apprentice-design/` and `/tmp/apprentice-final-design/`.
- Live Supabase SQL tests passed: authenticated owner access, peer isolation, spoof rejection, update/delete restrictions, private storage policy, anonymous denial, required snapshot fields, atomic failed-save rollback, save and paired deletion. Both test transactions were fully rolled back. Security advisor returned no findings after all three migrations.
- Browser account/save/open/delete/upload tests mock cloud HTTP; they do not establish real email delivery. Production Site URL and redirect allowlist were verified in the signed-in Supabase dashboard after reload. Real mailbox confirmation and real Meta inference remain pending.

Current source `762f432fe12513f8daef8b08e8d3bbc96806482d` passed both GitHub CI jobs: https://github.com/ryanfer123/Meta-Hackathon/actions/runs/40546782597. Render deployment `dep-dbgdi9oae00c73d0piog` is live. The connected browser loaded the new homepage, checked all image/sample responses (200), sought to the skipped cap in the hosted workstation, and opened its working account form. No document overflow was observed. All 24 Playwright checks also passed against the deployed Render site; account/database/storage HTTP remains mocked in the cloud UI tests.

## Previous release evidence (historical)


## Automated evidence

- Python suite: 82 passing checks after the orchestration additions. Uses synthetic masks, a generated one-bit SAM fixture, actual local image encoding/decoding and mocked model edges. No live network calls.
- The production FastAPI static mount serves the built UI, bundled sample and health endpoint; all three were checked with TestClient after a production build.
- Ruff checks/format and strict mypy pass on the application; React/TypeScript production build passes.
- Playwright: 16 desktop/mobile checks pass. Paths cover all six scenarios, actual playback progress, seeking, step predicates, preserved uncertainty, pending validation, chain verification and wrong-root rejection, report access, downloads and page overflow.
- GitHub Linux backend checks passed on the first publication. Initial frontend CI exposed overlapping timeline markers; the corrected revision groups nearby events. GitHub Checks run #2 passed for source commit `4a0d842515f1fc1edd93df7b5c7d036749672cde`: https://github.com/ryanfer123/Meta-Hackathon/actions/runs/40533926377.
- GitHub Pages failed to create the site with `Resource not accessible by integration`; this is a deployment permission failure. The workflow is now opt-in until repository Pages is enabled.

Fresh public clone verification passed: locked Python install, replay API without keys, locked npm install, and production frontend build.

## Browser and visual verification

Primary browser: Chrome DevTools connector. Loaded the local app, inspected the accessibility tree and computed dimensions, sought to the skipped-cap event, opened Audit and verified its chain. Checked the responsive layout and page scroll width.

The interactive browser window clamped to 500 px minimum width and 780 px content height. For exact dimensions, Playwright Chromium captured a 1505 × 1045 desktop viewport (the design reference's native size) and 390 × 844 mobile viewport. These captures supplement, rather than replace, the primary-browser interaction checks. All three views were rendered and inspected.

Local design reference: `docs/design-concept.png`, generated with the built-in imagegen tool. Prompt: a complete Apprentice supervision workstation with dark green-black canvas, lime accent, Learn/Supervise/Audit navigation, labelled synthetic tabletop, four-step tracker, alert, playback and evidence ledger. It is a design reference, not footage or model evidence.

Local rendered captures: `docs/ui-desktop-final.png`, `docs/ui-mobile-final.png`, `docs/ui-learn-final.png`, `docs/ui-audit-final.png`. The reference and latest desktop render were both opened with `view_image` in the final comparison pass; other rendered views and mobile were inspected too. These QA images stay local and are ignored by Git.

## Fidelity ledger

| Point | Reference | Implemented and checked |
|---|---|---|
| Copy / navigation | Every step. Accounted for.; Learn / Supervise / Audit; three primary actions | Headline, subtitle, tab order and action labels retained |
| Palette | #111512 canvas, #d5fa65 lime, muted green borders, red deviation | CSS tokens checked; no decorative glow or extra hero badges |
| Typography | Large heading, deliberate app controls, clear numbered steps | Heading scale increased after first comparison; controls and small annotations explicitly sized |
| Layout | Large left observation surface, right four-step tracker, full-width ledger | Grid retained; responsive view stacks with no document overflow |
| Scene / evidence | Synthetic tabletop with colored tubes, labels and dropper | Code-native SVG derived from actual synthetic mask coordinates; mask overlays change during replay |
| Interaction | Playback and evidence access | Real time state, pause/reset/seek, inspectable predicates, alerts, reports and chain checks tested |
| Defect repair | Event markers must be clickable | Same-time markers overlapped; grouping and larger targets fixed the browser failure |

Intentional differences: a scenario selector and provenance explanations are required functional controls; SVG geometry is simpler than the generated concept's perspective rendering; scene positions and event text come from executable fixtures; cap wording avoids implying tightness; the ledger contains all actual engine events and can be taller than the concept. Mobile tables scroll within their own containers.

Above-the-fold copy diff: main headline, subtitle, navigation and action labels match. Added workspace/scenario/overlay labels are functional controls. No accuracy, latency or fabricated inference claim is present. The implementation was visually verified against the reference for these surfaces and intentional differences; no remaining clipping or overlapping control was observed.

## Hosted verification

Render deployment `dep-dbgcuji9lscs739n0s80` is live at https://apprentice-meta.onrender.com for source commit `4a0d842515f1fc1edd93df7b5c7d036749672cde`. In the connected Chrome browser, the hosted app rendered, skipped-cap seeking updated the correct step and alert, all six sample JSON files returned HTTP 200 with synthetic provenance, the audit verified its chain, and the standalone HTML report returned HTTP 200. Document overflow was false. Initial CDN asset propagation briefly returned 404s; reloading after propagation loaded the normal URLs successfully. The static site intentionally has no live API.

## Remaining evidence

Real model calls, GPU serving, expert recordings, held-out/counterfactual success on real data, frozen-test results and the final filmed demo require their own verification. Synthetic and mocked checks cannot establish those outcomes.
