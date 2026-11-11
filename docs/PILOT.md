# One procedure, measured honestly

Target user: a lab teaching assistant reviewing visible handling during a classroom serial-dilution exercise with colored water. This is a proposed user setting; no user trial or endorsement has occurred.

## Record

Use one fixed top-down camera, steady lighting, a plain background, visibly different cap/label colors, a contrasting dropper and a clearly marked tray/holder. No faces, names, screens or identifying background. Record only with participants' consent; keep originals under ignored `data/` or outside the repository.

Use one short procedure: open a distinctly marked tube and park its cap in the tray; bring the dropper to that tube; return the dropper to its holder; replace the cap. Narrate each action and object name. The system checks visible handling, not liquid volume, concentration, sterility or cap tightness. Do not add unobservable requirements to the protocol.

1. Record teaching A and a genuinely different clean take B. Review the proposed steps and boundaries. Run native video tracking and all validation checks. A failed check is a finding to investigate, not a badge to bypass.
2. Inspect object masks. Record the tracking duration, request count, estimated/reserved cost, objects lost and the time ranges that are unknown. Fix object visibility or protocol discriminativeness before recording a polished demo.
3. Record two dev takes (one clean, one deliberate mistake). Label them before viewing predictions. Tune only on dev.
4. Record four to six separate test takes: include clean, skipped cap/return, wrong item or order as appropriate. Label and freeze them before evaluating. Do not cut one recording into multiple supposedly independent takes.

## Label without looking at predictions

Create separate folders for dev/test footage and predictions. Use the actual local protocol path in every command below. The labelling page reads only the manifest/protocol and the local video you choose; it never opens prediction files or calls a provider.

```sh
uv run python scripts/make_manifest.py --videos data/pilot/dev --predictions data/pilot/predictions/dev --out data/pilot/labels.json --split dev --reference-video data/pilot/expert-a.mp4 --reference-video data/pilot/expert-b.mp4
uv run python scripts/make_manifest.py --videos data/pilot/test --predictions data/pilot/predictions/test --out data/pilot/labels.json --split test
uv run python scripts/label_recordings.py --manifest data/pilot/labels.json --protocol data/pilot/protocol.json --out data/pilot/label.html
```

Open the generated HTML locally, choose each matching recording, seek to each mistake, select the affected step/type and add the timestamp. Check every recording, including clean takes, then download the confirmed labels. For skipped/order events, use the moment the later step completes, not an earlier moment when an action was omitted. Evaluation tolerance is ±2 seconds around that definition.

```sh
uv run python scripts/label_recordings.py --manifest data/pilot/labels.json --import-labels path/to/labels.confirmed.json --protocol data/pilot/protocol.json
uv run python eval/run_eval.py --pilot --protocol data/pilot/protocol.json --manifest data/pilot/labels.json --frozen data/pilot/frozen.json --freeze
```

The frozen manifest includes both dev and test labels; do not change it after freezing. Use a new version if a genuine correction is needed. Pilot mode requires 6–8 independently labelled recordings, at least two dev and four test, and distinct teaching/second-video reference hashes. It refuses teaching/validation footage in the evaluation. The original larger evaluation mode still requires six dev and six test recordings.

## Run, then report

```sh
uv run python scripts/run_batch.py --protocol data/pilot/protocol.json --videos data/pilot/dev --out data/pilot/predictions/dev --split dev --max-cost-usd 5 --allow-paid-calls
# Tune on dev, then freeze the test manifest as above. Do not tune after viewing test results.
uv run python scripts/run_batch.py --protocol data/pilot/protocol.json --videos data/pilot/test --out data/pilot/predictions/test --split test --max-cost-usd 5 --allow-paid-calls
uv run python eval/run_eval.py --pilot --protocol data/pilot/protocol.json --manifest data/pilot/labels.json --frozen data/pilot/frozen.json --out eval/results.md
```

Choose native video mode in local configuration for this experiment. Reservations are refusal thresholds, not invoices. Report counts, per-type precision/recall/F1 and uncertainty, unconfirmed steps, latency and estimated costs. Keep failures in the report. One successful clip and synthetic tests do not establish accuracy.

## One actual user

Invite one consenting lab TA to teach/check a recording using the app without coaching their clicks. Record: task, date, consent, what they tried, where they hesitated, whether the finding helped, one direct quote (only with permission), and one resulting change. Ask whether they would use it again and why. Do not contact anyone or publish their footage/feedback without authorization. This section is a trial plan, not evidence that a trial happened.
