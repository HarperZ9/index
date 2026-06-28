"""Budgeted context envelopes for large-codebase agent work."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..graph.build import DependencyGraph
from .pack import closure, focus_subgraph, preservation, to_json

SCHEMA = "project-telos.context-envelope/v1"
TOOL = "index.context.envelope"
BYTES_PER_TOKEN = 4


def build_context_envelope(
    graph: DependencyGraph,
    *,
    root: Path | str,
    token_budget: int,
    focus: str | None = None,
    hops: int | None = None,
) -> dict:
    """Return a deterministic, receipt-backed context packet within ``token_budget``."""
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    source_graph = graph
    preserved = None
    if focus:
        names = {node.name for node in graph.repos}
        if focus not in names:
            raise ValueError(f"unknown focus repo: {focus}")
        keep = closure(list(graph.edges), focus, hops=hops)
        preserved = preservation(list(graph.edges), keep, focus, hops)
        graph = focus_subgraph(graph, keep)
    pack = to_json(graph)
    pack_hash = _sha(pack)
    retained: list[dict] = []
    omitted: list[dict] = []
    approx_tokens = _base_tokens(pack)
    source_refs = _source_refs(pack)
    for repo in _ranked_repos(pack):
        item = _repo_item(repo, pack, source_refs.get(repo["name"], []))
        cost = _approx_tokens(item)
        if approx_tokens + cost <= token_budget or not retained:
            retained.append(item)
            approx_tokens += cost
        else:
            omitted.append(_omitted(repo["name"], "budget_exceeded", cost))
    omitted.extend(_focus_omissions(source_graph, graph))
    failure_codes = ["context_budget_exceeded"] if any(
        item["reason"] == "budget_exceeded" for item in omitted
    ) else []
    verdict = "UNVERIFIABLE" if failure_codes else "MATCH"
    return {
        "schema": SCHEMA,
        "tool": TOOL,
        "verification_verdict": verdict,
        "failure_codes": failure_codes,
        "root": str(Path(root)),
        "focus": {"repo": focus, "hops": hops},
        "budget": {
            "token_budget": token_budget,
            "approx_tokens": min(approx_tokens, token_budget),
            "bytes_per_token": BYTES_PER_TOKEN,
        },
        "retained": retained,
        "omitted": _dedupe_omitted(omitted),
        "preserved": preserved,
        "receipts": [{"kind": "graph-pack", "sha256": pack_hash, "schema": "index.context/graph-pack"}],
        "privacy": {"raw_source_included": False, "source_refs_only": True},
        "recheck": {"command": "index context-envelope --json", "graph_pack_sha256": pack_hash},
    }


def _ranked_repos(pack: dict) -> list[dict]:
    sal = pack.get("salience", {})
    return sorted(
        pack.get("repos", []),
        key=lambda repo: (
            -sal.get(repo["name"], {}).get("in_degree", 0),
            -sal.get(repo["name"], {}).get("out_degree", 0),
            repo["name"],
        ),
    )


def _repo_item(repo: dict, pack: dict, source_refs: list[str]) -> dict:
    sal = pack.get("salience", {}).get(repo["name"], {"in_degree": 0, "out_degree": 0})
    return {
        "name": repo["name"],
        "roles": pack.get("roles", {}).get(repo["name"], []),
        "ecosystems": repo.get("ecosystems", []),
        "description": repo.get("description", ""),
        "salience": {"in_degree": sal.get("in_degree", 0), "out_degree": sal.get("out_degree", 0)},
        "source_refs": source_refs or ["graph:repo"],
    }


def _source_refs(pack: dict) -> dict[str, list[str]]:
    refs: dict[str, set[str]] = {}
    for rel in pack.get("relations", []):
        for endpoint in (rel.get("from"), rel.get("to")):
            if endpoint:
                refs.setdefault(str(endpoint), set())
        for sig in rel.get("signals", []):
            ref = sig.get("file")
            if ref and rel.get("from"):
                line = sig.get("line")
                refs[str(rel["from"])].add(f"{ref}:{line}" if line else str(ref))
    return {name: sorted(values) for name, values in refs.items()}


def _focus_omissions(source: DependencyGraph, focused: DependencyGraph) -> list[dict]:
    kept = {node.name for node in focused.repos}
    return [_omitted(node.name, "outside_focus_or_budget", 0)
            for node in source.repos if node.name not in kept]


def _omitted(name: str, reason: str, approx_tokens: int) -> dict:
    return {"name": name, "reason": reason, "approx_tokens": approx_tokens}


def _dedupe_omitted(items: list[dict]) -> list[dict]:
    out: dict[str, dict] = {}
    for item in items:
        out.setdefault(item["name"], item)
    return sorted(out.values(), key=lambda item: item["name"])


def _base_tokens(pack: dict) -> int:
    return _approx_tokens({
        "schema": SCHEMA,
        "relations": len(pack.get("relations", [])),
        "cycles": pack.get("cycles", []),
        "warnings": pack.get("warnings", []),
    })


def _approx_tokens(value: object) -> int:
    return max(1, len(json.dumps(value, sort_keys=True, separators=(",", ":"))) // BYTES_PER_TOKEN)


def _sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
