"""Lens pack: the context envelope plus the data needed to REPLAY it live.

The envelope is a receipt; the lens makes it visible. To let the page vary the
token budget without re-running Python, the pack carries exactly what the
envelope algorithm consumes: the ranked repo order, each item's approximate
token cost, and the base cost. The page replays the same greedy rule
(`envelope.py`: retain while base + costs fits, first item always retained)
over the same numbers, so what the slider shows is what the CLI would emit,
never an approximation of it.

Honest scope: the replay varies BUDGET only. Focus/hops change the candidate
set itself and require a re-run; the pack records the focus it was built with.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..graph.build import DependencyGraph
from .envelope import (
    _approx_tokens,
    _base_tokens,
    _ranked_repos,
    _repo_item,
    _source_refs,
    build_context_envelope,
)
from .focus import resolve_focus
from .pack import closure, focus_subgraph, to_json

SCHEMA = "project-telos.context-lens/v1"
TOOL = "index.context.lens"


def replay_retained(order: list[dict], base_tokens: int, token_budget: int) -> list[str]:
    """The SAME greedy rule as build_context_envelope, over the pack's numbers.
    This function is the contract the page's JS mirrors; the lens test holds
    both against the real envelope output."""
    retained: list[str] = []
    approx = base_tokens
    for item in order:
        if approx + item["cost"] <= token_budget or not retained:
            retained.append(item["name"])
            approx += item["cost"]
    return retained


def build_lens_pack(
    graph: DependencyGraph,
    *,
    root: Path | str,
    token_budget: int,
    focus: str | None = None,
    hops: int | None = None,
) -> dict:
    """Envelope + replay data + node metadata, one deterministic pack."""
    envelope = build_context_envelope(
        graph, root=root, token_budget=token_budget, focus=focus, hops=hops)
    scoped = graph
    if focus:
        names = {node.name for node in graph.repos}
        resolved = resolve_focus(focus, names)
        scoped = focus_subgraph(
            graph, closure(list(graph.edges), resolved, hops=hops))
    pack = to_json(scoped)
    refs = _source_refs(scoped, Path(root).resolve())
    order = []
    for repo in _ranked_repos(pack, envelope["focus"]["repo"]):
        item = _repo_item(repo, pack, refs.get(repo["name"], []))
        order.append({
            "name": item["name"],
            "cost": _approx_tokens(item),
            "roles": item["roles"],
            "description": item["description"],
            "salience": item["salience"],
            "source_refs": item["source_refs"],
        })
    lens = {
        "schema": SCHEMA,
        "tool": TOOL,
        "envelope": envelope,
        "replay": {
            "rule": "greedy-in-rank-order; retain while base+costs fit; first item always retained",
            "base_tokens": _base_tokens(pack),
            "order": order,
        },
        "edges": [
            {"from": e["from"], "to": e["to"]}
            for e in pack.get("relations", []) if not e.get("external")
        ],
    }
    lens["receipt_sha256"] = _sha(lens)
    return lens


def _sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
