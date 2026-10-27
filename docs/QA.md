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
