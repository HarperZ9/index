"""The context manifest: the defined handoff seam for downstream consumers."""
from __future__ import annotations

import hashlib
import json
from collections import Counter


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def render_manifest(pack: dict, *, artifacts: dict, meta: dict) -> dict:
    snapshot = json.dumps(pack, sort_keys=True, separators=(",", ":")).encode("utf-8")
    role_counts = Counter(
        (rs or ["isolated"])[0] for rs in pack.get("roles", {}).values()
    )
    renders = {
        key: {"path": path, "sha256": _sha(data)}
        for key, (path, data) in artifacts.items()
        if key in ("mermaid", "svg", "html")
    }
    out = {
        "schema_version": "1",
        "generated": {
            "tool": "index",
            "version": meta.get("version", ""),
            "commit": meta.get("commit"),
            "root": meta.get("root", ""),
        },
        "graph": {
            "node_count": len(pack.get("repos", [])),
            "edge_count": len(pack.get("relations", [])),
            "roles": dict(role_counts),
            "snapshot_sha256": _sha(snapshot),
        },
        "renders": renders,
        "receipts": {"present": False},
    }
    if "context" in artifacts:
        path, data = artifacts["context"]
        out["context_pack"] = {"path": path, "sha256": _sha(data)}
    return out
