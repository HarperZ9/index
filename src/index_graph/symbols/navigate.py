"""Symbol-graph navigation: go-to-definition, find-references, find-implementations.

A pure query layer over the wave-1 ``SymbolGraph`` plus resolved inheritance
edges. Every result carries file:line evidence, and every verdict defers to the
graph's own resolution so nothing is guessed:

  - definitions: symbols whose id or bare name matches the query.
  - references: resolved callers of the matched symbols, plus a separate,
    honestly-labeled list of unresolved same-name references (never callers).
  - implementations: for a class query, its resolved subclasses; for a method
    query, the in-repo overrides of that method. A bare method name resolves
    against every matching definition so ``Base.method`` and ``method`` both work.

The query is a symbol id (``module::name`` or ``Class::method``) or a bare name.
"""
from __future__ import annotations

from .inheritance import InheritanceEdge
from .model import SymbolDefinition, SymbolGraph


def _matches(sym: SymbolDefinition, query: str) -> bool:
    """A symbol matches a query by exact id, bare name, or a ``Class::method`` tail."""
    if sym.id == query or sym.name == query:
        return True
    # A `Class::method` or `module::name` tail lets a partial id resolve.
    return sym.id.endswith("::" + query)


def find_definitions(graph: SymbolGraph, query: str) -> list[dict]:
    """Go-to-definition: every matching symbol with its file:line site."""
    return [
        {"id": s.id, "name": s.name, "kind": s.kind, "module_id": s.module_id,
         "file": s.file, "line": s.line, "is_public": s.is_public}
        for s in graph.symbols if _matches(s, query)
    ]


def find_references(graph: SymbolGraph, query: str) -> dict:
    """Find-references: resolved callers (evidence-backed) + unresolved refs.

    A resolved caller names a real call edge whose target is a matched symbol.
    An unresolved reference shares the bare name but bound to no edge; it is
    reported separately and never counted as a caller.
    """
    targets = {s.id for s in graph.symbols if _matches(s, query)}
    names = {s.name for s in graph.symbols if _matches(s, query)}
    references = [
        {"from_symbol": c.from_symbol, "to_symbol": c.to_symbol,
         "to_name": c.to_name, "file": c.evidence_file, "line": c.evidence_line,
         "raw": c.raw, "resolution": c.resolution, "confidence": c.confidence}
        for c in graph.calls if c.to_symbol in targets
    ]
    references.sort(key=lambda r: (r["file"], r["line"], r["from_symbol"]))
    unresolved = [
        {"from_symbol": c.from_symbol, "to_name": c.to_name,
         "file": c.evidence_file, "line": c.evidence_line, "raw": c.raw}
        for c in graph.calls if c.to_symbol is None and c.to_name in names
    ]
    unresolved.sort(key=lambda r: (r["file"], r["line"], r["from_symbol"]))
    return {"references": references, "unresolved": unresolved}


def find_implementations(
    graph: SymbolGraph, edges: list[InheritanceEdge], query: str,
) -> dict:
    """Find-implementations: subclasses of a class, or overrides of a method.

    Resolution is by the matched definition's kind. A class query returns the
    ``subclass`` edges whose parent is a matched class. A method query returns
    the ``override`` edges whose parent is a matched method. When a query
    matches both (rare bare-name collisions), both lists are populated honestly.
    """
    class_targets = {s.id for s in graph.symbols
                     if _matches(s, query) and s.kind == "class"}
    method_targets = {s.id for s in graph.symbols
                      if _matches(s, query) and s.kind in ("method", "async_method")}
    subclasses = [_edge_row(e) for e in edges
                  if e.kind == "subclass" and e.parent in class_targets]
    overrides = [_edge_row(e) for e in edges
                 if e.kind == "override" and e.parent in method_targets]
    subclasses.sort(key=lambda r: (r["file"], r["line"], r["child"]))
    overrides.sort(key=lambda r: (r["file"], r["line"], r["child"]))
    return {"subclasses": subclasses, "overrides": overrides}


def _edge_row(e: InheritanceEdge) -> dict:
    return {"child": e.child, "parent": e.parent, "name": e.name,
            "file": e.file, "line": e.line, "resolution": e.resolution}
