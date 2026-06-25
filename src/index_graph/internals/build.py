"""Assemble an InternalGraph: modules, internal edges, cycles, fan-in/out, coverage."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..graph.edges import Edge
from ..graph.cycles import find_cycles
from .modules import ModuleNode, InternalEdge, Unresolved, discover_modules, _extract


@dataclass(frozen=True)
class Coverage:
    """How structurally complete the module graph is, and what it could not see.
    A verdict over this graph is sound only for what coverage marks resolved
    (call-graph soundness: static analysis cannot see dynamic dispatch or
    unparseable files, so it must say so rather than imply completeness)."""
    modules: int
    internal_edges: int
    parse_errors: tuple[str, ...]
    dynamic_imports: tuple[tuple[str, int | None], ...]

    @property
    def complete(self) -> bool:
        return not self.parse_errors and not self.dynamic_imports


@dataclass(frozen=True)
class InternalGraph:
    repo: str
    modules: tuple[ModuleNode, ...]
    edges: tuple[InternalEdge, ...]
    cycles: tuple[tuple[str, ...], ...]
    fan_in: dict[str, int]
    fan_out: dict[str, int]
    coverage: Coverage


def _cycles(edges: tuple[InternalEdge, ...]) -> tuple[tuple[str, ...], ...]:
    # Reuse the repo-level Tarjan SCC by constructing minimal internal Edges;
    # find_cycles reads only from_repo/to_repo/external.
    as_edges = [Edge(e.from_id, e.to_id, e.to_id, False, "high", ()) for e in edges]
    return tuple(find_cycles(as_edges))


def _coverage(modules: tuple[ModuleNode, ...], edges: tuple[InternalEdge, ...],
              unresolved: list[Unresolved]) -> Coverage:
    return Coverage(
        modules=len(modules),
        internal_edges=len(edges),
        parse_errors=tuple(sorted({u.file for u in unresolved if u.reason == "parse_error"})),
        dynamic_imports=tuple((u.file, u.line) for u in unresolved if u.reason == "dynamic"),
    )


def build_internals(repo_root: Path, repo_name: str | None = None) -> InternalGraph:
    root = repo_root.resolve()
    name = repo_name or root.name
    modules = tuple(discover_modules(root))
    edge_list, unresolved = _extract(root, list(modules))
    edges = tuple(edge_list)
    fan_out: dict[str, int] = {}
    fan_in: dict[str, int] = {}
    seen_out: set[tuple[str, str]] = set()
    seen_in: set[tuple[str, str]] = set()
    for e in edges:
        if (e.from_id, e.to_id) not in seen_out:
            seen_out.add((e.from_id, e.to_id))
            fan_out[e.from_id] = fan_out.get(e.from_id, 0) + 1
        if (e.to_id, e.from_id) not in seen_in:
            seen_in.add((e.to_id, e.from_id))
            fan_in[e.to_id] = fan_in.get(e.to_id, 0) + 1
    return InternalGraph(name, modules, edges, _cycles(edges), fan_in, fan_out,
                         _coverage(modules, edges, unresolved))
