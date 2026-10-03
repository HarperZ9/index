"""The navigator: one typed question per level, branching on the answer.

At each inner node the chooser sees only that node's children, offered as a
map. Every child whose probability is at least ``ratio`` times the top child's
is followed (at most ``beam`` of them), and the followed probabilities are
renormalized so a confident single choice costs nothing. Children not followed
go to a backlog; when every followed branch is spent before enough files are
found, the navigator backtracks to the most probable backlog entry. Nodes are expanded
best first by path probability. Leaves are emitted in that order until they
cover ``max_files`` distinct files. Only leaves reach the caller's context.

The result carries the decision path: every question asked, the distribution
the chooser returned, and which children were followed, so a run can be
replayed and audited offline.
"""
from __future__ import annotations

import heapq
import itertools

from .chooser import Chooser, is_flat
from .maps import Map, MapEntry
from .outline import Node, Outline
from .text import approx_tokens

PATH_SCHEMA = "index.decision-path/v1"
DEFAULT_RATIO = 0.5
DEFAULT_BEAM = 4
MAX_QUESTIONS = 400


def children_map(node: Node) -> Map:
    """The children of ``node`` as a map: names for the model, nodes for the code."""
    seen: dict[str, int] = {}
    entries = []
    for child in node.children:
        count = seen.get(child.name, 0)
        seen[child.name] = count + 1
        name = child.name if count == 0 else f"{child.name}#{count + 1}"
        entries.append(MapEntry(name=name, description=child.description, handle=child))
    return Map(entries)


def follow(dist: list[float], ratio: float, beam: int) -> list[int]:
    """Indexes to follow: at least ``ratio`` of the top probability, best first, capped."""
    if not dist:
        return []
    top = max(dist)
    keep = [i for i, p in enumerate(dist) if p >= ratio * top]
    keep.sort(key=lambda i: (-dist[i], i))
    return keep[:max(beam, 1)]


def _ask(query: str, node: Node, chooser: Chooser, ratio: float, beam: int):
    options = children_map(node)
    dist = chooser.choose(query, options)
    picked = follow(dist, ratio, beam)
    mass = sum(dist[i] for i in picked) or 1.0
    step = {"node": node.id or ".", "options": options.names(),
            "distribution": [round(p, 6) for p in dist],
            "followed": [options.names()[i] for i in picked], "flat": is_flat(dist)}
    cost = approx_tokens(query) + sum(approx_tokens(e["name"] + " " + e["description"])
                                      for e in options.for_model())
    kept = [(options.entries[i].handle, dist[i] / mass) for i in picked]
    deferred = [(e.handle, dist[i]) for i, e in enumerate(options.entries) if i not in picked]
    return step, cost, kept, deferred


def first_per_file(leaves: list) -> list:
    """Keep the first entry for each file, in order. Entries are (node, ...) tuples or nodes."""
    seen: set[str] = set()
    out = []
    for item in leaves:
        node = item[0] if isinstance(item, tuple) else item
        if node.file not in seen:
            seen.add(node.file)
            out.append(item)
    return out


def navigate(outline: Outline, query: str, chooser: Chooser, *, ratio: float = DEFAULT_RATIO,
             beam: int = DEFAULT_BEAM, max_files: int = 5, all_leaves: bool = False) -> dict:
    """Walk ``outline`` for ``query``; return leaves, the decision path and token costs.

    By default the context receives the first leaf reached in each file, which
    is that file's most probable leaf. ``all_leaves`` delivers every reached leaf.
    """
    tie = itertools.count()
    frontier: list = [(-1.0, next(tie), outline.root)]
    backlog: list = []
    leaves: list[tuple[Node, float]] = []
    files: list[str] = []
    steps: list[dict] = []
    question_tokens = 0
    while (frontier or backlog) and len(files) < max_files and len(steps) < MAX_QUESTIONS:
        neg, _, node = heapq.heappop(frontier or backlog)
        if node.is_leaf:
            if node.kind in ("dir", "file"):
                continue
            leaves.append((node, -neg))
            if node.file not in files:
                files.append(node.file)
            continue
        step, cost, kept, deferred = _ask(query, node, chooser, ratio, beam)
        steps.append(step)
        question_tokens += cost
        for child, p in kept:
            heapq.heappush(frontier, (neg * p, next(tie), child))
        for child, p in deferred:
            heapq.heappush(backlog, (neg * p, next(tie), child))
    if not all_leaves:
        leaves = first_per_file(leaves)
    return {
        "query": query, "chooser": chooser.name, "ratio": ratio, "beam": beam,
        "files": files,
        "leaves": [{"id": n.id, "file": n.file, "start": n.start, "end": n.end,
                    "kind": n.kind, "probability": round(p, 6)} for n, p in leaves],
        "tokens_shown": sum(approx_tokens(n.text) for n, _ in leaves),
        "question_tokens": question_tokens,
        "path": {"schema": PATH_SCHEMA, "steps": steps},
        "_leaf_nodes": [n for n, _ in leaves],
    }
