"""Grounding handlers: verify, freshness, bench, mcp."""

from __future__ import annotations

import json

from .. import __version__
from ..context.pack import to_json
from ..graph.build import build_graph
from ._common import repo_paths, require_dir


def cmd_watch(args) -> int:
    """Auto-resync: hold the prior fingerprint, recompute on each tick, emit a
    live FRESH/STALE receipt on change, and (optionally) regenerate an artifact."""
    import time as _time

    from ..freshness.watch import watch_iter
    from ._common import rel_to_root

    if args.interval <= 0:
        raise SystemExit("watch: --interval must be positive")
    root = require_dir(args.root)

    def _paths():
        return repo_paths(root)

    regen = None
    if args.regen:
        regen = _make_regen(args, root, rel_to_root)

    max_ticks = args.max_ticks if args.max_ticks and args.max_ticks > 0 else None
    changed = 0
    try:
        for report in watch_iter(_paths(), interval=args.interval,
                                  max_ticks=max_ticks):
            if args.json:
                print(json.dumps(report), flush=True)
            elif report["tick"] == 0:
                print(f"watching {root} — baseline {report['curr_root'][:12]}… "
                      f"(every {args.interval}s; Ctrl-C to stop)", flush=True)
            else:
                deltas = (report.get("repos_changed", []) +
                          ["+" + a for a in report.get("repos_added", [])] +
                          ["-" + r for r in report.get("repos_removed", [])])
                print(f"[tick {report['tick']}] {report['verdict']}: "
                      f"{', '.join(deltas) or report.get('error', '—')}", flush=True)
            if regen and report["tick"] > 0 and report["verdict"] == "STALE":
                out = regen()
                if not args.json:
                    print(f"           regenerated {out}", flush=True)
            if report["tick"] > 0 and report["verdict"] == "STALE":
                changed += 1
    except KeyboardInterrupt:
        if not args.json:
            print(f"\nstopped — {changed} resync(s) detected", flush=True)
    return 0


def _make_regen(args, root, rel_to_root):
    """Return a zero-arg callable that regenerates the requested artifact and
    returns its path. Reuses the same builders the one-shot subcommands use."""
    from pathlib import Path

    from ..knowledge.docs import discover_docs

    out = Path(args.out or f"index-{args.regen}.html")

    def _run():
        paths = repo_paths(root)
        graph = build_graph(paths)
        if args.regen == "workbench":
            from ..viz.workbench_html import render_workbench_html
            from ..workbench import build_workbench_pack
            repo_dirs = {n: rel_to_root(root, p) for n, p in paths.items()}
            wb = build_workbench_pack(graph, discover_docs(root), repo_dirs, root=root)
            out.write_text(render_workbench_html(wb), encoding="utf-8")
        elif args.regen == "atlas":
            from .. import viz
            from ..knowledge.atlas import build_atlas_pack
            docs = discover_docs(root)
            repo_dirs = {n: rel_to_root(root, p) for n, p in paths.items()}
            pack = build_atlas_pack(graph, docs, repo_dirs)
            svg = viz.render_atlas_svg(viz.build_atlas_layout(pack))
            out.write_text(viz.render_atlas_html(pack, docs, svg=svg), encoding="utf-8")
        return str(out)

    return _run


def cmd_verify(args) -> int:
    from ..verify import build_verification

    root = require_dir(args.root)
    if (args.depends is None) == (args.exists is None):
        raise SystemExit(
            "verify: pass exactly one of --depends 'A -> B' or --exists NAME"
        )
    if args.exists is not None and not args.exists.strip():
        raise SystemExit("verify: --exists NAME must be non-empty")
    if args.depends:
        if "->" not in args.depends:
            raise SystemExit("verify: --depends must be 'A -> B'")
        frm, to = (s.strip() for s in args.depends.split("->", 1))
        claim = {"kind": "depends", "from": frm, "to": to}
        recheck = f'index verify --root "{args.root}" --depends "{args.depends}"'
    else:
        claim = {"kind": "exists", "name": args.exists.strip()}
        recheck = f'index verify --root "{args.root}" --exists "{args.exists}"'
    pack = to_json(build_graph(repo_paths(root)))
    rec = build_verification(pack, claim, tool_version=__version__, recheck=recheck)
    if args.json:
        print(json.dumps(rec, indent=2, sort_keys=True))
    else:
        loc = f" ({rec['evidence']})" if rec["evidence"] else ""
        print(f"verdict={rec['verdict']}: {rec['detail']}{loc}")
    return {"MATCH": 0, "REFUTED": 1, "UNVERIFIABLE": 2}[rec["verdict"]]


def cmd_freshness(args) -> int:
    from ..freshness import REPORT_SCHEMA, compare_freshness, workspace_fingerprint

    root = require_dir(args.root)
    try:
        cert = json.loads(args.cert.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"freshness: cannot read certificate {args.cert}: {exc}")
    stamp = cert.get("freshness") if isinstance(cert, dict) else None
    if not stamp:
        report = {
            "schema": REPORT_SCHEMA,
            "verdict": "UNVERIFIABLE",
            "detail": "certificate carries no freshness stamp "
            "(mint it with index check --freshness)",
        }
    else:
        try:
            report = compare_freshness(stamp, workspace_fingerprint(repo_paths(root)))
        except ValueError as exc:
            report = {
                "schema": REPORT_SCHEMA,
                "verdict": "UNVERIFIABLE",
                "detail": str(exc),
            }
    report["recheck"] = f'index freshness --cert "{args.cert}" --root "{args.root}"'
    return _freshness_emit(args, report)


def _freshness_emit(args, report) -> int:
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        line = f"verdict={report['verdict']}"
        if report.get("detail"):
            line += f": {report['detail']}"
        print(line)
        for n in report.get("repos_changed", []):
            print(f"  changed: {n}")
        for n in report.get("repos_added", []):
            print(f"  added: {n}")
        for n in report.get("repos_removed", []):
            print(f"  removed: {n}")
    return {"FRESH": 0, "STALE": 1, "UNVERIFIABLE": 2}[report["verdict"]]


def cmd_bench(args) -> int:
    from ..bench import bench_workspace

    root = require_dir(args.root)
    report = bench_workspace(repo_paths(root))
    report["recheck"] = f"index bench --root {args.root}"
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        st, pk = report["source_bytes"], report["pack_bytes"]
        red = report["reduction"]
        red_txt = f"  {red}x smaller" if red else ""
        print("token economy: index's structural pack vs the source it reads")
        print(
            f"  source read   {st:>11,} bytes  (~{report['approx_tokens_source']:,} "
            f"tokens)  {report['source_files']} files in {report['repos']} repos"
        )
        print(
            f"  index pack    {pk:>11,} bytes  "
            f"(~{report['approx_tokens_pack']:,} tokens){red_txt}"
        )
        f = report["faithfulness"]
        print(
            f"  faithfulness  {f['edge_grounding'] * 100:.0f}% of "
            f"{f['internal_edges']} kept edges grounded in file:line source "
            f"(the reduction fabricates nothing)"
        )
        print(
            f"  note: ~{report['bytes_per_token']} bytes/token is an approximation; "
            "the reduction ratio does not depend on it."
        )
        print(
            "        the pack answers structural questions (depends-on, roles, "
            "cycles); reading the code is still needed for behavior."
        )
    return 0


def cmd_mcp(args) -> int:
    from ..mcp import serve

    return serve()
