# Apprentice engineering contract
The current user authorizes the complete implementation, commits, pushes and a public web demo. The pasted milestone-only stop instruction is superseded by that request. Keys and physical recordings will be supplied later: never invent observations, model calls, evaluation results or validation badges.

- Web app: Python 3.11+, FastAPI, Pydantic v2, React, Vite, TypeScript.
- All hosted Meta calls go through backend/app/meta_client.py. Glimmer calls go through glimmer_client.py.
- Models propose; pixels ground; predicates.py and supervise/state_machine.py alone decide step completion.
- Strict schema validation, maximum two retries after an initial malformed model response.
- Deterministic tests use synthetic masks and mocked transports. No live calls in ordinary tests.
- Run pytest, ruff, mypy --strict and frontend build before pushing implementation changes.
- Never commit secrets, raw private recordings, .env, or generated local run data.
- Budget caps must be enforced before requests. Replay is explicitly synthetic unless provenance proves otherwise.
- Report occlusion as uncertainty. Geometry cannot establish liquid concentration, volume or transfer.
- Do not claim tamper-proof auditing. A local hash chain requires a separately trusted root.
- Keep evaluation dev/test separate; real-world performance remains pending until real labelled recordings exist.
