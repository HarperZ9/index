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


def bench_workspace(repo_paths: dict[str, Path]) -> dict:
    """The bytes index reads vs the bytes of the structural pack it emits.

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
    }
