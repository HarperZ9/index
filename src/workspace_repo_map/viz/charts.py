"""Three compact HTML+CSS bar charts derived purely by counting the pack."""
from __future__ import annotations

from collections import Counter
from xml.sax.saxutils import escape

_PRECEDENCE = ("entrypoint", "orchestrator", "hub", "library", "leaf", "isolated")


def _primary(roles: list[str]) -> str:
    for r in _PRECEDENCE:
        if r in roles:
            return r
    return "isolated"


def _bars(pairs: list[tuple[str, int]]) -> str:
    top = max((v for _, v in pairs), default=0) or 1
    rows = []
    for label, value in pairs:
        pct = round(100 * value / top)
        rows.append(
            f'<div class="row"><span class="lbl">{escape(label)}</span>'
            f'<span class="bar" style="width:{pct}%" data-label="{escape(label)}" '
            f'data-count="{value}"></span><span class="num">{value}</span></div>'
        )
    return '<div class="chart">' + "".join(rows) + "</div>"


def render_charts(pack: dict) -> dict[str, str]:
    rels = pack.get("relations", [])
    conf = Counter(r.get("confidence", "low") for r in rels)
    confidence = _bars([(k, conf.get(k, 0)) for k in ("high", "moderate", "low")])

    roles = pack.get("roles", {})
    role_counts = Counter(_primary(list(roles.get(r["name"], ()))) for r in pack.get("repos", []))
    role_chart = _bars([(k, role_counts[k]) for k in _PRECEDENCE if role_counts[k]])

    sal = pack.get("salience", {})
    fan_in = sorted(sal.items(), key=lambda kv: (-kv[1].get("in_degree", 0), kv[0]))[:5]
    fan_out = sorted(sal.items(), key=lambda kv: (-kv[1].get("out_degree", 0), kv[0]))[:5]
    fanio = (
        '<h4>Most depended-on</h4>'
        + _bars([(k, v.get("in_degree", 0)) for k, v in fan_in])
        + '<h4>Most dependencies</h4>'
        + _bars([(k, v.get("out_degree", 0)) for k, v in fan_out])
    )
    return {"confidence": confidence, "roles": role_chart, "fanio": fanio}
