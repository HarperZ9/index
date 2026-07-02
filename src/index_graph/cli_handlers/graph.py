"""Graph-shaped handlers: graph, internals, viz."""

from __future__ import annotations

import json
from pathlib import Path

from .. import __version__
from ..context.focus import focus_rejection, render_rejection
from ..context.pack import closure, focus_subgraph, render_text, to_json
from ..graph.build import build_graph
from ._common import head_commit, repo_paths, require_dir


def cmd_graph(args) -> int:
    graph = build_graph(repo_paths(args.root.resolve()))
    if getattr(args, "cycles", False):
        from ..graph.cycles import find_cycles

        cycles = find_cycles(graph.edges)
        if args.json:
            print(json.dumps({"cycles": [list(c) for c in cycles]}, indent=2))
        elif not cycles:
            print("no cycles, a clean DAG")
        else:
            print(f"{len(cycles)} cycle(s):")
            for c in cycles:
                print(f"  - {' -> '.join(c)} -> {c[0]}")
        return 0
    if args.json:
        print(json.dumps(to_json(graph), indent=2))
    else:
        print(render_text(graph, "dependency graph"))
    return 0


def cmd_internals(args) -> int:
    from ..internals import build_internals

    root = require_dir(args.root)
    g = build_internals(root)
    if getattr(args, "cycles", False):
        return _internals_cycles(args, g)
    payload = _internals_payload(g)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        cov = (
            "complete"
            if g.coverage.complete
            else f"{len(g.coverage.parse_errors)} unparsed, "
            f"{len(g.coverage.dynamic_imports)} dynamic"
        )
        print(
            f"modules={len(g.modules)} edges={len(g.edges)} "
            f"cycles={len(g.cycles)} coverage={cov}"
        )
    return 0


def _internals_cycles(args, g) -> int:
    if args.json:
        print(json.dumps({"cycles": [list(c) for c in g.cycles]}, indent=2))
    elif not g.cycles:
        print("no internal cycles - clean DAG")
    else:
        print(f"{len(g.cycles)} internal cycle(s):")
        for c in g.cycles:
            print(f"  - {' -> '.join(c)}")
    return 0


def _internals_payload(g) -> dict:
    return {
        "repo": g.repo,
        "modules": [
            {"id": m.id, "path": m.path, "language": m.language} for m in g.modules
        ],
        "edges": [
            {
                "from": e.from_id,
                "to": e.to_id,
                "file": e.evidence_file,
                "line": e.evidence_line,
                "raw": e.raw,
            }
            for e in g.edges
        ],
        "cycles": [list(c) for c in g.cycles],
        "fan_in": g.fan_in,
        "fan_out": g.fan_out,
        "coverage": {
            "complete": g.coverage.complete,
            "modules": g.coverage.modules,
            "internal_edges": g.coverage.internal_edges,
            "parse_errors": list(g.coverage.parse_errors),
            "dynamic_imports": [
                {"file": fpath, "line": ln} for fpath, ln in g.coverage.dynamic_imports
            ],
        },
    }


def cmd_viz(args) -> int:
    from .. import viz

    graph = build_graph(repo_paths(args.root.resolve()))
    names = {n.name for n in graph.repos}
    if args.focus:
        if args.focus not in names:
            print(render_rejection(focus_rejection(args.focus, names)))
            return 2
        graph = focus_subgraph(graph, closure(list(graph.edges), args.focus))
    pack = to_json(graph)
    include_external = not args.no_external

    def _svg() -> str:
        return viz.render_svg(viz.build_layout(pack, include_external=include_external))

    def _html() -> str:
        return viz.render_html(
            pack,
            svg=_svg(),
            charts=viz.render_charts(pack, include_external=include_external),
        )

    if args.format == "all":
        return _viz_all(args, viz, pack, include_external, _svg, _html)
    text = {
        "svg": _svg,
        "mermaid": lambda: viz.render_mermaid(pack, include_external=include_external),
        "html": _html,
    }[args.format]()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


def _viz_all(args, viz, pack, include_external, _svg, _html) -> int:
    out_dir = Path(args.out_dir or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "graph.mmd": viz.render_mermaid(pack, include_external=include_external).encode(
            "utf-8"
        ),
        "graph.svg": _svg().encode("utf-8"),
        "graph.html": _html().encode("utf-8"),
        "context.json": json.dumps(pack, indent=2).encode("utf-8"),
    }
    for name, data in files.items():
        (out_dir / name).write_bytes(data)
    artifacts = {
        "mermaid": ("graph.mmd", files["graph.mmd"]),
        "svg": ("graph.svg", files["graph.svg"]),
        "html": ("graph.html", files["graph.html"]),
        "context": ("context.json", files["context.json"]),
    }
    meta = {
        "version": __version__,
        "commit": head_commit(args.root.resolve()),
        "root": str(args.root),
    }
    manifest = viz.render_manifest(pack, artifacts=artifacts, meta=meta)
    (out_dir / "context-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return 0
