"""Token economy: how much smaller is index's structural pack than the source it reads.

The thesis the research converges on (a structural map is cheaper than letting an
agent read files) is here turned into a number anyone can reproduce on their own
workspace. index reads the manifests and sources of every ecosystem to build the
graph; it emits one compact structural pack. This measures the ratio between the two.

Bytes are exact and model-agnostic. The token figures use the common ~4 bytes/token
approximation, but the reduction RATIO is independent of that constant (it divides out),
so the headline number does not depend on any tokenizer.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..context.pack import to_json
from ..freshness.fingerprint import relevant_files
from ..graph.build import build_graph

SCHEMA = "index.bench/1"
BYTES_PER_TOKEN = 4  # common ~4 bytes/token approximation; the reduction ratio does not depend on it


def _source_bytes(repo_paths: dict[str, Path]) -> tuple[int, int]:
    """Total bytes and file count of the graph-relevant files index reads."""
    total = files = 0
    for root in repo_paths.values():
        for p in relevant_files(root):
            try:
                total += p.stat().st_size
            except OSError:
                continue
            files += 1
    return total, files


def _compact_bytes(obj) -> int:
    return len(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _grounding(pack: dict) -> dict:
    """Faithfulness of the reduction: what fraction of the internal dependency
    edges the compact pack KEEPS are backed by real file:line source evidence.

    A byte reduction is only honest if it fabricates nothing. grep-and-truncate
    or an LLM summary can drop or invent structure; index's every retained edge
    cites the import that produced it. This turns 'the reduction is faithful'
    into a measured number, not a promise: grounded internal edges / internal
    edges. 1.0 means every structural fact kept is provably in the source."""
    internal = [r for r in pack.get("relations", []) if not r.get("external")]
    grounded = [r for r in internal
                if any(s.get("file") for s in r.get("signals", []))]
    total = len(internal)
    return {
        "internal_edges": total,
        "grounded_edges": len(grounded),
        "edge_grounding": round(len(grounded) / total, 4) if total else 1.0,
        "note": ("fraction of kept dependency edges carrying file:line evidence; "
                 "1.0 = the reduction fabricates no structure"),
    }


def bench_workspace(repo_paths: dict[str, Path]) -> dict:
    """The bytes index reads vs the bytes of the structural pack it emits, AND
    the faithfulness of that reduction (every kept edge grounded in source).

    Deterministic for a fixed workspace, so the report is re-checkable like every
    other index verdict.
    """
    src_bytes, n_files = _source_bytes(repo_paths)
    pack = to_json(build_graph(repo_paths))
    pack_bytes = _compact_bytes(pack)
    reduction = round(src_bytes / pack_bytes, 1) if pack_bytes else None
    return {
        "schema": SCHEMA,
        "repos": len(repo_paths),
        "source_files": n_files,
        "source_bytes": src_bytes,
        "pack_bytes": pack_bytes,
        "reduction": reduction,
        "bytes_per_token": BYTES_PER_TOKEN,
        "approx_tokens_source": src_bytes // BYTES_PER_TOKEN,
        "approx_tokens_pack": pack_bytes // BYTES_PER_TOKEN,
        "faithfulness": _grounding(pack),
    }
