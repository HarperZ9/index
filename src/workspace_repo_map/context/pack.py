"""Render a DependencyGraph as the synthesis context pack (relations+roles+prose).

No editorializing: every line traces to a data field or an evidence record.
"""
from __future__ import annotations

from ..graph.build import DependencyGraph, RepoNode
from ..graph.edges import Edge
from ..graph.roles import salience_audit, structural_salience


def _marker_list(node: RepoNode) -> list[str]:
    out = []
    if "entry" in node.markers:
        out.append("entry")
    if "published" in node.markers:
        out.append("published")
    return out


def render_text(graph: DependencyGraph, title: str) -> str:
    L = [f"# Context pack: {title}", ""]
    L.append("## Roles (project: roles — in/out degree)")
    sal = structural_salience(list(graph.edges))
    for node in sorted(graph.repos, key=lambda n: n.name):
        rs = ", ".join(graph.roles.get(node.name, ())) or "(none)"
        s = sal.get(node.name, {"in_degree": 0, "out_degree": 0})
        L.append(f"- {node.name}: {rs} — in={s['in_degree']} out={s['out_degree']}")
    L.append("")
    L.append("## Relations (A -> B: signals [confidence])")
    for e in graph.edges:
        if e.external:
            continue
        kinds = "+".join(sorted({s.kind for s in e.signals}))
        L.append(f"- {e.from_repo} -> {e.to_repo}: {kinds} [{e.confidence}]")
    L.append("")
    L.append("## External dependencies (A -> name)")
    for e in graph.edges:
        if e.external:
            L.append(f"- {e.from_repo} -> {e.target_name}")
    L.append("")
    L.append("## Inventory (all projects — extracted description)")
    for node in sorted(graph.repos, key=lambda n: n.name):
        eco = "/".join(node.ecosystems) or "none"
        L.append(f"- {node.name} [{eco}]: {node.description}")
    L.append("")
    if graph.warnings:
        L.append(f"## Warnings ({len(graph.warnings)})")
        for w in graph.warnings:
            L.append(f"- {w}")
    return "\n".join(L)


def to_json(graph: DependencyGraph) -> dict:
    sal = structural_salience(list(graph.edges))
    marked = {n.name: _marker_list(n) for n in graph.repos if _marker_list(n)}
    relations = [{
        "from": e.from_repo, "to": e.to_repo, "target_name": e.target_name,
        "external": e.external, "confidence": e.confidence,
        "signals": [{"kind": s.kind, "file": s.evidence_file, "line": s.evidence_line,
                     "raw": s.raw_spec} for s in e.signals],
    } for e in graph.edges]
    return {
        "roles": {n.name: list(graph.roles.get(n.name, ())) for n in graph.repos},
        "relations": relations,
        "salience": sal,
        "salience_audit": salience_audit(sal, marked),
        "repos": [{"name": n.name, "ecosystems": list(n.ecosystems),
                   "description": n.description, "markers": sorted(n.markers)}
                  for n in graph.repos],
        "warnings": list(graph.warnings),
    }


def closure(edges: list[Edge], focus: str) -> set[str]:
    adj: dict[str, set[str]] = {}
    for e in edges:
        if e.external or e.to_repo is None:
            continue
        adj.setdefault(e.from_repo, set()).add(e.to_repo)
        adj.setdefault(e.to_repo, set()).add(e.from_repo)
    seen = {focus}
    stack = [focus]
    while stack:
        n = stack.pop()
        for m in adj.get(n, ()):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


def focus_subgraph(graph: DependencyGraph, keep: set[str]) -> DependencyGraph:
    repos = tuple(n for n in graph.repos if n.name in keep)
    edges = tuple(e for e in graph.edges
                  if e.from_repo in keep and (e.external or e.to_repo in keep))
    roles = {k: v for k, v in graph.roles.items() if k in keep}
    return DependencyGraph(repos, edges, roles, graph.warnings)
