"""Export rule-engine outputs; these are synthetic, never recorded model responses."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.audit.chain import build_chain  # noqa: E402
from app.audit.report import render_report  # noqa: E402
from app.replay_cache import atomic_json  # noqa: E402
from app.samples import SAMPLES, sample_run  # noqa: E402


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "frontend/public/samples"
    target.mkdir(parents=True, exist_ok=True)
    for name in SAMPLES:
        run = sample_run(name)
        chain, root = build_chain(run["events"], {})
        run["chain"], run["chain_root"] = chain, root
        atomic_json(target / f"{name}.json", run)
        (target / f"{name}.html").write_text(render_report(run, root))
        print(f"Exported synthetic scenario: {name}")


if __name__ == "__main__":
    main()
