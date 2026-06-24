"""Render the pack to a Mermaid flowchart (Mermaid performs its own layout)."""
from __future__ import annotations

import re

from .theme import ROLE_COLOR

_PRECEDENCE = ("entrypoint", "orchestrator", "hub", "library", "leaf", "isolated")


def _primary(roles: list[str]) -> str:
    for r in _PRECEDENCE:
        if r in roles:
            return r
    return "isolated"


def _mid(name: str) -> str:
    return "n_" + re.sub(r"[^0-9A-Za-z]", "_", name)


def render_mermaid(pack: dict) -> str:
    roles = pack.get("roles", {})
    lines = ["flowchart TD"]
    # deterministic node declarations
    internal = sorted(r["name"] for r in pack.get("repos", []))
    externals = sorted({r["target_name"] for r in pack.get("relations", []) if r.get("external")})
    node_role: dict[str, str] = {}
    for name in internal:
        primary = _primary(list(roles.get(name, ())))
        node_role[name] = primary
        lines.append(f'    {_mid(name)}["{name}"]')
    for name in externals:
        node_role[name] = "external"
        lines.append(f'    {_mid(name)}(("{name}"))')
    # edges, deterministic order
    rels = sorted(
        pack.get("relations", []),
        key=lambda r: (r["from"], r["target_name"], r.get("confidence", "")),
    )
    for r in rels:
        target = r["target_name"] if r.get("external") else r["to"]
        kinds = "+".join(sorted({s.get("kind", "") for s in r.get("signals", [])})) or "?"
        conf = r.get("confidence", "low")
        lines.append(f'    {_mid(r["from"])} -->|{conf} ({kinds})| {_mid(target)}')
    # classDefs + assignments
    for role, color in ROLE_COLOR.items():
        lines.append(f"    classDef {role} fill:{color},stroke:#0d1b1c,color:#e9e2d0;")
    for name in internal + externals:
        lines.append(f"    class {_mid(name)} {node_role[name]};")
    return "\n".join(lines) + "\n"
