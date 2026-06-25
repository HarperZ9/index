"""Canonical, minimal, sorted projection of a context pack for drift diffing."""
from __future__ import annotations

import json


def snapshot_pack(pack: dict) -> dict:
    edges = sorted(
        f"{r['from']} -> {r['to']}"
        for r in pack.get("relations", [])
        if not r.get("external") and r.get("to")
    )
    roles = {k: list(v) for k, v in sorted(pack.get("roles", {}).items())}
    cycles = sorted(tuple(sorted(c)) for c in pack.get("cycles", []))
    repos = sorted(roles.keys())
    return {
        "schema": "index.snapshot/1",
        "repos": repos,
        "edges": edges,
        "roles": roles,
        "cycles": [list(c) for c in cycles],
    }


def dumps_canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def load_snapshot(text: str) -> dict:
    return json.loads(text)
