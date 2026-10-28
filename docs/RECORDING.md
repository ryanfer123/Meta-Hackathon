# Record evidence for the real demonstration

Use colored water only. Choose a blue-labeled tube, red/yellow/green neighboring tubes, blue cap, white label, dropper and holder. Use a tripod, fixed camera, plain background, consistent visible hands and good lighting. Keep each observed contact visible for at least 1.5 seconds at 2 fps. No medical, biological or hazardous materials.

1. Record Expert A (narrated, <=90 seconds). Demonstrate dropper contact with tube 1, return to holder, cap contact with tube 1, and label placement. Say only what is visibly demonstrated. Do not claim that contact proves a transfer.
2. Record Expert B separately, changing placement and lighting. Keep it out of protocol compilation.
3. Record six dev takes: two clean, skipped cap, swapped actions, wrong tube, partial occlusion or slow handling. Label action/event type, step ID and timestamp before looking at predictions.
4. Record six or more independent test takes, including a second person if available. Keep test videos and labels untouched during development. Record feedback only when actually obtained, with consent.
5. Label exact Expert A boundaries per compiled step: `{ "approach": { "start": 2, "end": 5.5 } }`. The start must precede the action, the end must include its postcondition. Ranges must be ordered and nonoverlapping for adjacent swaps.
6. Run Learn, upload A, inspect the JSON, upload B and ranges, then validate. Four checks must pass before `verified=true`. Keep failures and repair history.
7. Supervise each novice recording. Save run JSON as the manifest's `prediction` path. Source video hashes must match. Edit `eval/labels.json` with independently labelled runs and `source: "real"`.
8. Freeze once: `uv run python eval/run_eval.py --freeze`. Commit the freeze metadata before test inference/analysis. Then run `uv run python eval/run_eval.py`. No threshold tuning based on test results.

Do not commit recordings without consent. `eval/runs/dev` and `eval/runs/test` are for private data. Download public model call summaries only after inspecting them for private content. The three-minute submission video should show real held-out evidence and measured results, not promote synthetic smoke checks as scientific validation.

## Batch manifest and timestamp conventions

Label each deviation with its exact protocol step ID and the engine's observable trigger time. `skipped` and `out_of_order` are emitted when the later step's postcondition becomes stably true, not at an earlier instant when the operator physically omitted an action. For `skipped`, use the omitted step's ID; for `out_of_order`, use the later completed step's ID. Apply the evaluator's ±2 s tolerance to that trigger definition. Review clean runs and deliberately leave their event lists empty. Never infer ground-truth timestamps from predictions.

Use the manifest and batch commands in [README](../README.md#batch-recording-workflow-t4). Keep recordings and generated artifacts in ignored private folders. The manifest helper never watches footage or labels events; confirm each real-source entry yourself before evaluation.
