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


def _id_map(names):
    out, used = {}, set()
    for name in names:  # names arrive in a stable (sorted) order
        base = "n_" + re.sub(r"[^0-9A-Za-z]", "_", name)
        ident, i = base, 1
        while ident in used:
            ident, i = f"{base}_{i}", i + 1
        used.add(ident)
        out[name] = ident
    return out


def render_mermaid(pack: dict) -> str:
    roles = pack.get("roles", {})
    lines = ["flowchart TD"]
    # deterministic node declarations
    internal = sorted(r["name"] for r in pack.get("repos", []))
    externals = sorted({r["target_name"] for r in pack.get("relations", []) if r.get("external")})
    ids = _id_map(internal + externals)
    node_role: dict[str, str] = {}
    for name in internal:
        primary = _primary(list(roles.get(name, ())))
        node_role[name] = primary
        lines.append(f'    {ids[name]}["{name}"]')
    for name in externals:
        node_role[name] = "external"
        lines.append(f'    {ids[name]}(("{name}"))')
    # edges, deterministic order
    rels = sorted(
        pack.get("relations", []),
        key=lambda r: (r["from"], (r["target_name"] if r.get("external") else r["to"]), r.get("confidence", "")),
    )
    for r in rels:
        target = r["target_name"] if r.get("external") else r["to"]
        kinds = {s["kind"] for s in r.get("signals", []) if s.get("kind")}
        conf = r.get("confidence", "low")
        if kinds:
            label = f'{conf} ({"+".join(sorted(kinds))})'
            lines.append(f'    {ids[r["from"]]} -->|{label}| {ids[target]}')
        else:
            lines.append(f'    {ids[r["from"]]} -->|{conf}| {ids[target]}')
    # classDefs + assignments
    for role, color in ROLE_COLOR.items():
        lines.append(f"    classDef {role} fill:{color},stroke:#0d1b1c,color:#e9e2d0;")
    for name in internal + externals:
        lines.append(f"    class {ids[name]} {node_role[name]};")
    return "\n".join(lines) + "\n"
