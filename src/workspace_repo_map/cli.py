"""Command-line entry point: map (default) + graph + context subcommands."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__
from .config import load_config
from .context.pack import closure, focus_subgraph, render_text, to_json
from .graph.build import build_graph
from .scan import build_map, discover_repos, write_map

_SUBCOMMANDS = {"map", "graph", "context", "viz"}


def _add_map_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--jobs", type=int, default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-repo-map",
        description="Repository inventory maps + dependency graph + context packs.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    _add_map_args(sub.add_parser("map", help="Write the repository inventory map (default)."))

    g = sub.add_parser("graph", help="Derive the repo-level dependency graph.")
    g.add_argument("--root", type=Path, default=Path.cwd())
    g.add_argument("--json", action="store_true")

    c = sub.add_parser("context", help="Render the synthesis context pack.")
    c.add_argument("--root", type=Path, default=Path.cwd())
    c.add_argument("--json", action="store_true")
    c.add_argument("--focus", default=None)
    c.add_argument("--audit", action="store_true")

    v = sub.add_parser("viz", help="Render the dependency graph (html/svg/mermaid).")
    v.add_argument("--root", type=Path, default=Path.cwd())
    v.add_argument("--format", choices=["html", "svg", "mermaid", "all"], default="html")
    v.add_argument("--focus", default=None)
    v.add_argument("--no-external", action="store_true")
    v.add_argument("--out", default=None)
    v.add_argument("--out-dir", default=None)
    return parser


def _repo_paths(root: Path) -> dict[str, Path]:
    # discover_repos requires a Config; use neutral defaults for graph/context.
    config = load_config(None, root)
    return {p.name: p for p in discover_repos(root, config)}


def _cmd_map(args) -> int:
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    config = load_config(args.config, root)
    if args.jobs is not None:
        if args.jobs < 1:
            raise SystemExit("--jobs must be a positive integer")
        config = replace(config, jobs=args.jobs)
    if args.json:
        print(json.dumps(build_map(root, config, __version__).to_json(), indent=2))
    else:
        output = args.output.resolve() if args.output else root / "WORKSPACE-REPO-MAP.json"
        data = write_map(root, config, __version__, output)
        print(f"wrote {output}")
        print(f"repos={data.repo_count} dirty={data.dirty_count}")
    return 0


def _cmd_graph(args) -> int:
    graph = build_graph(_repo_paths(args.root.resolve()))
    if args.json:
        print(json.dumps(to_json(graph), indent=2))
    else:
        print(render_text(graph, "dependency graph"))
    return 0


def _cmd_context(args) -> int:
    graph = build_graph(_repo_paths(args.root.resolve()))
    names = {n.name for n in graph.repos}
    if args.audit:
        data = to_json(graph)
        print(f"salience-faithfulness warnings: {len(data['salience_audit'])}")
        for w in data["salience_audit"]:
            print(f"  [{w['kind']}] {w['node']} (in={w['in_degree']}) — {w['note']}")
        return 0
    if args.focus:
        if args.focus not in names:
            near = [n for n in names if args.focus.lower() in n.lower()]
            print(f"unknown project: {args.focus!r}"
                  + (f" — did you mean: {', '.join(sorted(near))}?" if near else ""))
            return 2
        graph = focus_subgraph(graph, closure(list(graph.edges), args.focus))
        title = f"focus={args.focus}"
    else:
        title = "workstation context"
    print(json.dumps(to_json(graph), indent=2) if args.json else render_text(graph, title))
    return 0


def _head_commit(root) -> str | None:
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _cmd_viz(args) -> int:
    from . import viz

    graph = build_graph(_repo_paths(args.root.resolve()))
    names = {n.name for n in graph.repos}
    if args.focus:
        if args.focus not in names:
            near = [n for n in names if args.focus.lower() in n.lower()]
            print(f"unknown project: {args.focus!r}"
                  + (f" — did you mean: {', '.join(sorted(near))}?" if near else ""))
            return 2
        graph = focus_subgraph(graph, closure(list(graph.edges), args.focus))
    pack = to_json(graph)
    include_external = not args.no_external

    def _svg() -> str:
        return viz.render_svg(viz.build_layout(pack, include_external=include_external))

    def _html() -> str:
        return viz.render_html(pack, svg=_svg(), charts=viz.render_charts(pack, include_external=include_external))

    if args.format == "all":
        out_dir = Path(args.out_dir or ".")
        out_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "graph.mmd": viz.render_mermaid(pack, include_external=include_external).encode("utf-8"),
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
        meta = {"version": __version__, "commit": _head_commit(args.root.resolve()), "root": str(args.root)}
        manifest = viz.render_manifest(pack, artifacts=artifacts, meta=meta)
        (out_dir / "context-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return 0

    text = {"svg": _svg, "mermaid": lambda: viz.render_mermaid(pack, include_external=include_external), "html": _html}[args.format]()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # No leading subcommand: route top-level --version/--help to the root
    # parser; otherwise treat the invocation as the implicit `map` command
    # (preserves v0.2.0 behavior).
    if not raw or raw[0] not in _SUBCOMMANDS:
        if raw and raw[0] in ("--version", "-h", "--help"):
            build_parser().parse_args(raw[:1])  # prints and exits
        raw = ["map", *raw]
    args = build_parser().parse_args(raw)
    if args.cmd == "graph":
        return _cmd_graph(args)
    if args.cmd == "context":
        return _cmd_context(args)
    if args.cmd == "viz":
        return _cmd_viz(args)
    return _cmd_map(args)
