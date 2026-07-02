"""Derive the verified-wiki pack from the real module graph of one repo.

Tier 1 by construction: zero-dependency, model-free, deterministic. Every
page is a projection of the internals graph (Python AST-exact, other
languages best-effort per docs/PROTOCOL.md) or of authored markdown joined
in verbatim. No prose is generated, and every edge shown carries the
file:line evidence the graph recorded for it.
"""
from __future__ import annotations

from pathlib import Path

from .. import __version__
from ..internals import InternalGraph, build_internals
from ..knowledge.docs import discover_docs
from ..knowledge.markdown import render_markdown
from ..viz import build_layout, render_mermaid, render_svg
from .seal import WIKI_SCHEMA, build_manifest, head_commit

# Above this module count the wiki collapses module pages into package pages.
CLUSTER_THRESHOLD = 120
_HUB_FAN_IN = 4


def _boundary(evidence_count: int) -> dict:
    return {"derived_from": "dependency-graph", "generated_prose": False,
            "evidence_count": evidence_count}


def _role(fan_in: int, fan_out: int) -> str:
    if fan_in == 0 and fan_out > 0:
        return "entrypoint"
    if fan_in >= _HUB_FAN_IN:
        return "hub"
    if fan_in == 0 and fan_out == 0:
        return "isolated"
    if fan_out == 0:
        return "leaf"
    return "library"


def _graph_pack(ids: list[str], languages: dict[str, str],
                pair_signals: dict[tuple[str, str], list[dict]],
                cycles: list[list[str]]) -> dict:
    """Shape a module or package graph like a context pack so the existing
    layout/SVG/mermaid renderers draw it unchanged."""
    fan_in: dict[str, int] = {}
    fan_out: dict[str, int] = {}
    for frm, to in pair_signals:
        fan_out[frm] = fan_out.get(frm, 0) + 1
        fan_in[to] = fan_in.get(to, 0) + 1
    roles, salience = {}, {}
    for node in ids:
        fi, fo = fan_in.get(node, 0), fan_out.get(node, 0)
        roles[node] = [_role(fi, fo)]
        salience[node] = {"in_degree": fi, "out_degree": fo, "hub": fi >= _HUB_FAN_IN}
    cycle_sets = [set(c) for c in cycles]
    relations = []
    for (frm, to), signals in sorted(pair_signals.items()):
        confidence = "high" if languages.get(frm) == "python" else "moderate"
        relations.append({"from": frm, "to": to, "target_name": to, "external": False,
                          "confidence": confidence, "signals": signals,
                          "in_cycle": any(frm in c and to in c for c in cycle_sets)})
    return {"repos": [{"name": n} for n in sorted(ids)], "relations": relations,
            "roles": roles, "salience": salience, "cycles": [list(c) for c in cycles]}


def _module_graph_pack(g: InternalGraph) -> dict:
    pairs: dict[tuple[str, str], list[dict]] = {}
    for e in g.edges:
        pairs.setdefault((e.from_id, e.to_id), []).append(
            {"kind": "import", "file": e.evidence_file,
             "line": e.evidence_line, "raw": e.raw})
    languages = {m.id: m.language for m in g.modules}
    return _graph_pack([m.id for m in g.modules], languages, pairs,
                       [list(c) for c in g.cycles])


def _package_of(module_id: str) -> str:
    return module_id.rsplit("/", 1)[0] if "/" in module_id else "(root)"


def _package_graph_pack(g: InternalGraph) -> dict:
    pairs: dict[tuple[str, str], list[dict]] = {}
    for e in g.edges:
        frm, to = _package_of(e.from_id), _package_of(e.to_id)
        if frm != to:
            pairs.setdefault((frm, to), []).append(
                {"kind": "import", "file": e.evidence_file,
                 "line": e.evidence_line, "raw": e.raw})
    members: dict[str, set[str]] = {}
    for m in g.modules:
        members.setdefault(_package_of(m.id), set()).add(m.language)
    languages = {pkg: ("python" if langs == {"python"} else "mixed")
                 for pkg, langs in members.items()}
    return _graph_pack(sorted(members), languages, pairs, [])


def _overview_page(g: InternalGraph, docs: list, commit: str) -> dict:
    entry_points = sorted(m.id for m in g.modules
                          if g.fan_in.get(m.id, 0) == 0 and g.fan_out.get(m.id, 0) > 0)
    return {"id": "overview", "kind": "overview", "title": f"{g.repo} overview",
            "repo": g.repo, "commit": commit,
            "ecosystems": sorted({m.language for m in g.modules}),
            "entry_points": entry_points,
            "module_count": len(g.modules), "internal_edge_count": len(g.edges),
            "cycle_count": len(g.cycles),
            "doc_count": len(docs), "doc_paths": [d.rel_path for d in docs],
            "coverage": {"complete": g.coverage.complete,
                         "parse_errors": list(g.coverage.parse_errors),
                         "dynamic_imports": [{"file": f, "line": ln}
                                             for f, ln in g.coverage.dynamic_imports]},
            "boundary": _boundary(0)}


def _module_pages(g: InternalGraph) -> list[dict]:
    imports_by: dict[str, list[dict]] = {}
    dependents_by: dict[str, list[dict]] = {}
    for e in g.edges:
        imports_by.setdefault(e.from_id, []).append(
            {"to": e.to_id, "file": e.evidence_file, "line": e.evidence_line, "raw": e.raw})
        dependents_by.setdefault(e.to_id, []).append(
            {"from": e.from_id, "file": e.evidence_file, "line": e.evidence_line, "raw": e.raw})
    pages = []
    for m in g.modules:
        imports = imports_by.get(m.id, [])
        dependents = dependents_by.get(m.id, [])
        pages.append({"id": f"module/{m.id}", "kind": "module", "title": m.id,
                      "module": m.id, "path": m.path, "language": m.language,
                      "imports": imports, "dependents": dependents,
                      "cycles": [list(c) for c in g.cycles if m.id in c],
                      "boundary": _boundary(len(imports) + len(dependents))})
    return pages


def _package_pages(g: InternalGraph) -> list[dict]:
    members: dict[str, list[str]] = {}
    for m in g.modules:
        members.setdefault(_package_of(m.id), []).append(m.id)
    outgoing: dict[str, dict[str, list[dict]]] = {}
    incoming: dict[str, dict[str, list[dict]]] = {}
    for e in g.edges:
        frm, to = _package_of(e.from_id), _package_of(e.to_id)
        if frm == to:
            continue
        via = {"from": e.from_id, "to": e.to_id,
               "file": e.evidence_file, "line": e.evidence_line}
        outgoing.setdefault(frm, {}).setdefault(to, []).append(via)
        incoming.setdefault(to, {}).setdefault(frm, []).append(via)
    pages = []
    for pkg in sorted(members):
        imports = [{"to": t, "via": v} for t, v in sorted(outgoing.get(pkg, {}).items())]
        dependents = [{"from": f, "via": v} for f, v in sorted(incoming.get(pkg, {}).items())]
        evidence = (sum(len(i["via"]) for i in imports)
                    + sum(len(d["via"]) for d in dependents))
        pages.append({"id": f"package/{pkg}", "kind": "package", "title": pkg,
                      "package": pkg, "modules": sorted(members[pkg]),
                      "imports": imports, "dependents": dependents,
                      "boundary": _boundary(evidence)})
    return pages


def _architecture_page(pack: dict, granularity: str, edge_count: int) -> dict:
    return {"id": "architecture", "kind": "architecture", "title": "Architecture",
            "granularity": granularity,
            "svg": render_svg(build_layout(pack, include_external=False)),
            "mermaid": render_mermaid(pack, include_external=False),
            "edge_count": edge_count, "cycles": pack["cycles"],
            "boundary": _boundary(edge_count)}


def _docs_page(docs: list) -> dict:
    entries = [{"path": d.rel_path, "title": d.title, "html": render_markdown(d.body)}
               for d in docs]
    return {"id": "docs", "kind": "docs", "title": "Docs",
            "provenance": "authored-by-humans", "docs": entries,
            "boundary": _boundary(0)}


def build_wiki_pack(root: Path | str, repo_name: str | None = None) -> dict:
    """The whole wiki as one sealed, portable, deterministic JSON pack."""
    root = Path(root).resolve()
    g = build_internals(root, repo_name)
    docs = discover_docs(root)
    commit = head_commit(root)
    clustered = len(g.modules) > CLUSTER_THRESHOLD
    if clustered:
        body = _package_pages(g)
        arch = _architecture_page(_package_graph_pack(g), "package", len(g.edges))
    else:
        body = _module_pages(g)
        arch = _architecture_page(_module_graph_pack(g), "module", len(g.edges))
    pages = [_overview_page(g, docs, commit), arch, *body, _docs_page(docs)]
    inputs = {"modules": len(g.modules), "internal_edges": len(g.edges),
              "docs": len(docs), "clustered": clustered,
              "coverage_complete": g.coverage.complete}
    manifest = build_manifest(pages, repo=g.repo, commit=commit,
                              inputs=inputs, tool_version=__version__)
    return {"schema": WIKI_SCHEMA, "repo": g.repo, "commit": commit,
            "pages": pages, "manifest": manifest}
