import base64
import html
import json
from typing import Any


def render_report(run: dict[str, Any], root: str, evidence: dict[str, bytes] | None = None) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    open_label = run.get("metrics", {}).get("open_tier_label", "glimmer")
    rows = "".join(
        f"<tr><td>{e['t']:.2f}s</td><td>{esc(e['step_id'])}</td><td>{esc(e['kind'])}</td>"
        f"<td>{esc(open_label if e['tier'] == 'glimmer' else e['tier'])}</td><td>{esc(e['detail'])}</td></tr>"
        for e in run["events"]
    )
    images = "".join(
        '<figure><img alt="Evidence frame" src="data:image/jpeg;base64,'
        + base64.b64encode(blob).decode()
        + '"><figcaption>'
        + esc(ref)
        + "</figcaption></figure>"
        for ref, blob in (evidence or {}).items()
    )
    steps = "".join(
        f"<tr><td>{esc(s['title'])}</td><td>{esc(run['states'].get(s['id'], 'PENDING'))}</td></tr>"
        for s in run["protocol"]["steps"]
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Apprentice audit - {esc(run["name"])}</title><style>
body{{font:16px/1.6 system-ui;background:#111512;color:#eef2e9;max-width:1100px;margin:40px auto;padding:24px}}
h1{{font-size:40px}} table{{width:100%;border-collapse:collapse}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #465044}}
code{{overflow-wrap:anywhere;color:#d5fa65}}img{{max-width:480px;width:100%}}pre{{white-space:pre-wrap}}figure{{display:inline-block}}
</style><h1>Apprentice / evidence audit</h1><p>{esc(run["name"])} · Provenance: {esc(run["provenance"])}</p>
<p>Observable handling only. Contact does not prove liquid transfer, volume or concentration.</p>
<h2>Steps</h2><table>{steps}</table><h2>Evidence ledger</h2><table><tr><th>Time</th><th>Step</th><th>Decision</th><th>Tier</th><th>Detail</th></tr>{rows}</table>
<h2>Bounded recovery</h2><p>One missing-object re-query may add pixel evidence; only replayed rules decide completion. Recovery notes are diagnostic and are not covered by the event-chain root.</p><pre>{esc(json.dumps(run.get("recovery_actions", []), indent=2))}</pre>
<h2>Metrics</h2><pre>{esc(json.dumps(run["metrics"], indent=2))}</pre><h2>Evidence</h2>{images or "<p>No real evidence images in this synthetic run.</p>"}
<h2>Chain root</h2><code>{esc(root)}</code><p>The local hash chain detects edits relative to a separately trusted root.
An editor can rewrite the chain and root together. Record this root separately. This is not tamper-proof.</p></html>"""
