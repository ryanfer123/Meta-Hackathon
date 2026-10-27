# Real-video evaluation: pending

No real expert or novice recordings were provided. No precision, recall, model latency, shadow agreement or egress percentage is claimed.

Record independent expert A/B takes and at least 6 dev + 6 test runs. Label errors before inspecting predictions. Tune only on dev; freeze the manifest and test-video hashes before evaluating the test set. See `docs/RECORDING.md` and `eval/run_eval.py`.

Synthetic fixtures and unit tests establish software behavior; they do not establish real-world accuracy or generalization.
