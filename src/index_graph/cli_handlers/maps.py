"""Knowledge-map handlers: atlas and router."""

from __future__ import annotations

import json
from pathlib import Path

from ..graph.build import build_graph
from ._common import rel_to_root, repo_paths, require_dir


def cmd_atlas(args) -> int:
    from ..knowledge.atlas import build_atlas_pack
    from ..knowledge.docs import discover_docs

    root = require_dir(args.root)
    paths = repo_paths(root)
    repo_dirs = {name: rel_to_root(root, p) for name, p in paths.items()}
    graph = build_graph(paths)
    docs = discover_docs(root)
    pack = build_atlas_pack(graph, docs, repo_dirs)
    if args.format == "html":
        return _atlas_html(args, pack, docs)
    if args.json:
        print(json.dumps(pack, indent=2))
    else:
        print(
            f"repos={len(pack['repos'])} docs={len(pack['docs'])} "
            f"knowledge_edges={len(pack['knowledge_edges'])}"
        )
    return 0


def cmd_workbench(args) -> int:
    from ..knowledge.docs import discover_docs
    from ..viz.workbench_html import render_workbench_html
    from ..workbench import build_workbench_pack

    if args.budget < 1:
        raise SystemExit("--budget must be a positive integer")
    root = require_dir(args.root)
    paths = repo_paths(root)
    repo_dirs = {name: rel_to_root(root, p) for name, p in paths.items()}
    graph = build_graph(paths)
    docs = discover_docs(root)
    wb = build_workbench_pack(
        graph, docs, repo_dirs,
        root=root, token_budget=args.budget, spine_dir=args.spine_dir,
        max_doc_bodies=args.max_doc_bodies)
    if args.json:
        print(json.dumps({k: v for k, v in wb.items() if k != "svg"},
                         indent=2, sort_keys=True))
        return 0
    page = render_workbench_html(wb)
    if args.out:
        Path(args.out).write_text(page, encoding="utf-8")
        s = wb["summary"]
        print(f"workbench -> {args.out}  ({s['repos']} repos, {s['docs']} docs, "
              f"{len(wb['spine']['tools'])} spine envelopes, "
              f"receipt {wb['receipt_sha256'][:16]}…)")
    else:
        print(page)
    return 0


def _atlas_html(args, pack, docs) -> int:
    from .. import viz

    include_external = not args.no_external
    svg = viz.render_atlas_svg(
        viz.build_atlas_layout(pack, include_external=include_external)
    )
    html = viz.render_atlas_html(pack, docs, svg=svg, include_external=include_external)
    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(html)
    return 0


def cmd_router(args) -> int:
    from ..knowledge.atlas import build_router_pack
    from ..knowledge.docs import discover_docs
    from ..router import render_router

    root = require_dir(args.root)
    paths = repo_paths(root)
    repo_dirs = {name: rel_to_root(root, p) for name, p in paths.items()}
    pack = build_router_pack(build_graph(paths), discover_docs(root), repo_dirs)
    text = render_router(pack)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0
