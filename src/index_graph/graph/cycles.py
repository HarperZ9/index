"""Detect dependency cycles (strongly-connected components) over internal edges.

Tarjan's SCC is linear; repo-level graphs are tiny (hundreds of nodes), so the
recursive form is safe and deterministic (inputs are sorted before traversal)."""
from __future__ import annotations

from collections.abc import Sequence

from .edges import Edge


def _adjacency(edges: Sequence[Edge]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for e in edges:
        if e.external or e.to_repo is None:
            continue
        adj.setdefault(e.from_repo, [])
        adj.setdefault(e.to_repo, [])
        if e.to_repo not in adj[e.from_repo]:
            adj[e.from_repo].append(e.to_repo)
    return adj


def find_cycles(edges: Sequence[Edge]) -> list[tuple[str, ...]]:
    """Node sets of each dependency cycle, deterministically sorted. An SCC with
    >1 node, or a self-loop, is a cycle; a pure DAG returns []."""
    adj = _adjacency(edges)
    self_loops = {e.from_repo for e in edges
                  if not e.external and e.to_repo == e.from_repo}
    counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    sccs: list[list[str]] = []

    def connect(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in adj.get(v, []):
            if w not in index:
                connect(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for v in sorted(adj):
        if v not in index:
            connect(v)

    cycles = [tuple(sorted(c)) for c in sccs
              if len(c) > 1 or (len(c) == 1 and c[0] in self_loops)]
    return sorted(cycles)


def cycle_edge_keys(edges: Sequence[Edge],
                    cycles: Sequence[tuple[str, ...]]) -> set[tuple[str, str]]:
    """(from, to) of internal edges whose endpoints share a cycle."""
    member: dict[str, tuple[str, ...]] = {n: c for c in cycles for n in c}
    return {(e.from_repo, e.to_repo) for e in edges
            if not e.external and e.to_repo is not None
            and e.from_repo in member and member[e.from_repo] == member.get(e.to_repo)}
