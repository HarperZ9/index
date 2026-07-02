"""Command-line entry point: map (default) + graph + context subcommands."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__
from .config import load_config
from .context.pack import closure, focus_subgraph, preservation, render_text, to_json
from .context.select import cmd_select
from .flagship import cmd_demo, cmd_doctor, cmd_status
from .graph.build import build_graph
from .scan import build_map, discover_repos, write_map

_SUBCOMMANDS = {"map", "graph", "context", "context-envelope", "select", "viz",
                "atlas", "internals", "check", "snapshot", "drift", "router",
                "verify", "freshness", "bench", "mcp", "status", "doctor", "demo"}


def _add_map_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--jobs", type=int, default=None)


def _add_select_parser(sub) -> None:
    se = sub.add_parser(
        "select", help="Select files under a root; every rejection carries a typed receipt.")
    se.add_argument("--root", type=Path, default=Path.cwd())
    se.add_argument("--suffix", dest="suffixes", action="append", default=None,
                    help="keep only files with this suffix (repeatable, e.g. --suffix .md)")
    se.add_argument("--max-files", type=int, default=None,
                    help="file budget; paths beyond it get over-budget receipts")
    se.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="index",
        description="Repository inventory maps + dependency graph + context packs.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    status = sub.add_parser("status", help="emit Index's Project Telos operator-spine status")
    status.add_argument("--json", action="store_true", help="emit a Project Telos action envelope")

    doctor = sub.add_parser("doctor", help="check Index's operator-spine readiness")
    doctor.add_argument("--json", action="store_true", help="emit a Project Telos action envelope")

    demo = sub.add_parser("demo", help="show Index's operator-spine demo command")
    demo.add_argument("--json", action="store_true", help="emit a Project Telos action envelope")

    _add_map_args(sub.add_parser("map", help="Write the repository inventory map (default)."))

    g = sub.add_parser("graph", help="Derive the repo-level dependency graph.")
    g.add_argument("--root", type=Path, default=Path.cwd())
    g.add_argument("--json", action="store_true")
    g.add_argument("--cycles", action="store_true",
                   help="Report dependency cycles instead of the full graph.")

    c = sub.add_parser("context", help="Render the synthesis context pack.")
    c.add_argument("--root", type=Path, default=Path.cwd())
    c.add_argument("--json", action="store_true")
    c.add_argument("--focus", default=None)
    c.add_argument("--hops", type=int, default=None)
    c.add_argument("--audit", action="store_true")

    ce = sub.add_parser("context-envelope", help="Emit a budgeted, receipt-backed context envelope.")
    ce.add_argument("--root", type=Path, default=Path.cwd())
    ce.add_argument("--budget", type=int, default=1200,
                    help="approximate token budget for retained context entries")
    ce.add_argument("--focus", default=None)
    ce.add_argument("--hops", type=int, default=None)
    ce.add_argument("--json", action="store_true")

    _add_select_parser(sub)

    v = sub.add_parser("viz", help="Render the dependency graph (html/svg/mermaid).")
    v.add_argument("--root", type=Path, default=Path.cwd())
    v.add_argument("--format", choices=["html", "svg", "mermaid", "all"], default="html")
    v.add_argument("--focus", default=None)
    v.add_argument("--no-external", action="store_true")
    v.add_argument("--out", default=None)
    v.add_argument("--out-dir", default=None)

    a = sub.add_parser("atlas", help="Two-layer code + knowledge map (repos + docs).")
    a.add_argument("--root", type=Path, default=Path.cwd())
    a.add_argument("--json", action="store_true")
    a.add_argument("--format", choices=["html"], default=None)
    a.add_argument("--out", default=None)
    a.add_argument("--no-external", action="store_true")

    i = sub.add_parser("internals", help="Intra-repo module dependency graph.")
    i.add_argument("--root", type=Path, default=Path.cwd())
    i.add_argument("--json", action="store_true")
    i.add_argument("--cycles", action="store_true")

    ck = sub.add_parser("check", help="Check structure against the declared [architecture] criterion.")
    ck.add_argument("--root", type=Path, default=Path.cwd())
    ck.add_argument("--internals", action="store_true", help="Include intra-repo module checks.")
    ck.add_argument("--freshness", action="store_true",
                    help="Stamp the certificate with a workspace content fingerprint.")
    ck.add_argument("--json", action="store_true")
    ck.add_argument("--config", type=Path, default=None)

    sn = sub.add_parser("snapshot", help="Write a canonical graph snapshot for drift diffing.")
    sn.add_argument("--root", type=Path, default=Path.cwd())
    sn.add_argument("--out", type=Path, required=True)

    dr = sub.add_parser("drift", help="Diff two snapshots into a drift report.")
    dr.add_argument("--from", dest="from_snap", type=Path, required=True)
    dr.add_argument("--to", dest="to_snap", type=Path, required=True)
    dr.add_argument("--json", action="store_true")

    rt = sub.add_parser("router", help="Emit a workspace map (CLAUDE.md/AGENTS.md) from the graph and docs.")
    rt.add_argument("--root", type=Path, default=Path.cwd())
    rt.add_argument("--out", default=None)

    vf = sub.add_parser("verify", help="Ground a structural claim against the graph (MATCH/REFUTED/UNVERIFIABLE).")
    vf.add_argument("--root", type=Path, default=Path.cwd())
    vf.add_argument("--depends", default=None, help="claim 'A -> B' (A depends on B)")
    vf.add_argument("--exists", default=None, help="claim that repo NAME exists")
    vf.add_argument("--json", action="store_true")

    fr = sub.add_parser("freshness",
                        help="Has the workspace changed since a certificate was minted? (FRESH/STALE).")
    fr.add_argument("--cert", type=Path, required=True,
                    help="A certificate JSON carrying a freshness stamp (index check --freshness).")
    fr.add_argument("--root", type=Path, default=Path.cwd())
    fr.add_argument("--json", action="store_true")

    bn = sub.add_parser("bench",
                        help="Token economy: index's structural pack vs reading the source it distills.")
    bn.add_argument("--root", type=Path, default=Path.cwd())
    bn.add_argument("--json", action="store_true")

    sub.add_parser("mcp", help="Serve the MCP-shaped stdio protocol face (JSON-RPC over stdin/stdout).")
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
        output = args.output.resolve() if args.output else root / "INDEX.json"
        data = write_map(root, config, __version__, output)
        print(f"wrote {output}")
        print(f"repos={data.repo_count} dirty={data.dirty_count}")
    return 0


def _cmd_atlas(args) -> int:
    from .knowledge.atlas import build_atlas_pack
    from .knowledge.docs import discover_docs
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    repo_paths = _repo_paths(root)

    def _rel(p: Path) -> str:
        r = p.resolve().relative_to(root).as_posix()
        return "" if r == "." else r          # a repo AT the root -> "" dir

    repo_dirs = {name: _rel(p) for name, p in repo_paths.items()}
    graph = build_graph(repo_paths)
    docs = discover_docs(root)
    pack = build_atlas_pack(graph, docs, repo_dirs)
    if args.format == "html":
        from . import viz
        include_external = not args.no_external
        svg = viz.render_atlas_svg(viz.build_atlas_layout(pack, include_external=include_external))
        html = viz.render_atlas_html(pack, docs, svg=svg, include_external=include_external)
        if args.out:
            Path(args.out).write_text(html, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(html)
        return 0
    if args.json:
        print(json.dumps(pack, indent=2))
    else:
        print(f"repos={len(pack['repos'])} docs={len(pack['docs'])} "
              f"knowledge_edges={len(pack['knowledge_edges'])}")
    return 0


def _cmd_graph(args) -> int:
    graph = build_graph(_repo_paths(args.root.resolve()))
    if getattr(args, "cycles", False):
        from .graph.cycles import find_cycles
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


def _cmd_context(args) -> int:
    if args.hops is not None and args.hops < 0:
        raise SystemExit("--hops must be >= 0")
    graph = build_graph(_repo_paths(args.root.resolve()))
    names = {n.name for n in graph.repos}
    if args.audit:
        data = to_json(graph)
        print(f"salience-faithfulness warnings: {len(data['salience_audit'])}")
        for w in data["salience_audit"]:
            print(f"  [{w['kind']}] {w['node']} (in={w['in_degree']}): {w['note']}")
        return 0
    preserved = None
    if args.focus:
        if args.focus not in names:
            near = [n for n in names if args.focus.lower() in n.lower()]
            print(f"unknown project: {args.focus!r}"
                  + (f". Did you mean: {', '.join(sorted(near))}?" if near else ""))
            return 2
        keep = closure(list(graph.edges), args.focus, hops=args.hops)
        preserved = preservation(list(graph.edges), keep, args.focus, args.hops)
        graph = focus_subgraph(graph, keep)
        title = f"focus={args.focus}" + (f" hops={args.hops}" if args.hops is not None else "")
    else:
        title = "workstation context"
    if args.json:
        pack = to_json(graph)
        if preserved is not None:
            pack["preserved"] = preserved
        print(json.dumps(pack, indent=2, sort_keys=True))
    else:
        text = render_text(graph, title)
        if preserved is not None:
            b = preserved["boundary"]
            text += (f"\n## Preserved\n- focus: {', '.join(preserved['focus'])}; "
                     f"hops: {preserved['hops']}; kept: {preserved['kept_nodes']} nodes\n"
                     f"- boundary dropped: {len(b['dropped_edges'])} edge(s) to "
                     f"{len(b['dropped_nodes'])} node(s)")
        print(text)
    return 0


def _cmd_context_envelope(args) -> int:
    if args.budget < 1:
        raise SystemExit("--budget must be a positive integer")
    if args.hops is not None and args.hops < 0:
        raise SystemExit("--hops must be >= 0")
    from .context.envelope import build_context_envelope
    graph = build_graph(_repo_paths(args.root.resolve()))
    try:
        env = build_context_envelope(
            graph,
            root=args.root.resolve(),
            token_budget=args.budget,
            focus=args.focus,
            hops=args.hops,
        )
    except ValueError as exc:
        print(str(exc))
        return 2
    if args.json:
        print(json.dumps(env, indent=2, sort_keys=True))
    else:
        print(f"context-envelope verdict={env['verification_verdict']} "
              f"tokens={env['budget']['approx_tokens']}/{env['budget']['token_budget']}")
        print(f"retained={len(env['retained'])} omitted={len(env['omitted'])}")
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
                  + (f". Did you mean: {', '.join(sorted(near))}?" if near else ""))
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


def _cmd_internals(args) -> int:
    from .internals import build_internals
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    g = build_internals(root)
    if getattr(args, "cycles", False):
        if args.json:
            print(json.dumps({"cycles": [list(c) for c in g.cycles]}, indent=2))
        elif not g.cycles:
            print("no internal cycles - clean DAG")
        else:
            print(f"{len(g.cycles)} internal cycle(s):")
            for c in g.cycles:
                print(f"  - {' -> '.join(c)}")
        return 0
    payload = {
        "repo": g.repo,
        "modules": [{"id": m.id, "path": m.path, "language": m.language} for m in g.modules],
        "edges": [{"from": e.from_id, "to": e.to_id, "file": e.evidence_file,
                   "line": e.evidence_line, "raw": e.raw} for e in g.edges],
        "cycles": [list(c) for c in g.cycles],
        "fan_in": g.fan_in, "fan_out": g.fan_out,
        "coverage": {
            "complete": g.coverage.complete,
            "modules": g.coverage.modules,
            "internal_edges": g.coverage.internal_edges,
            "parse_errors": list(g.coverage.parse_errors),
            "dynamic_imports": [{"file": fpath, "line": ln}
                                for fpath, ln in g.coverage.dynamic_imports],
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        cov = ("complete" if g.coverage.complete
               else f"{len(g.coverage.parse_errors)} unparsed, "
                    f"{len(g.coverage.dynamic_imports)} dynamic")
        print(f"modules={len(g.modules)} edges={len(g.edges)} "
              f"cycles={len(g.cycles)} coverage={cov}")
    return 0


def _emit_cert(cert: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(cert, indent=2, sort_keys=True))
    else:
        print(f"verdict={cert['verdict']} findings={len(cert['findings'])}")
        for f in cert["findings"]:
            loc = f" ({f['evidence']})" if f.get("evidence") else ""
            print(f"  [{f['rule']}] {f['detail']}{loc}")
        cov = cert.get("coverage")
        if cov is not None and not cov.get("complete", True):
            n = len(cov.get("unverifiable_repos", {}))
            print(f"  coverage: incomplete, {n} repo(s) with unverifiable regions")
    return 0 if cert["verdict"] == "MATCH" else 1


def _cmd_check(args) -> int:
    from .arch.check import check_graph
    from .certify import build_certificate
    from .context.pack import to_json
    from .freshness import workspace_fingerprint
    from .internals import build_internals
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    config = load_config(args.config, root)
    crit = config.architecture
    repo_paths = _repo_paths(root)
    graph = build_graph(repo_paths)
    pack = to_json(graph)
    names = set(pack.get("roles", {}).keys())
    fresh_stamp = workspace_fingerprint(repo_paths) if args.freshness else None
    fresh_flag = " --freshness" if args.freshness else ""

    if not crit.declared:
        cert = build_certificate(
            "check", content=pack, criterion=None, verdict="UNVERIFIABLE",
            findings=[{"rule": "criterion", "detail": "no [architecture] criterion declared",
                       "edge": None, "evidence": None}],
            recheck=f"index check --root {args.root}{fresh_flag}", tool_version=__version__,
            freshness=fresh_stamp)
        return _emit_cert(cert, args.json)

    # repo-level findings
    findings = [{"rule": f.rule, "detail": f.detail, "edge": f.edge, "evidence": f.evidence}
                for f in check_graph(pack, crit)]

    # optional intra-repo module checks: internal cycles against the ceiling
    internal_content = None
    if args.internals:
        internal_content = {}
        for name, p in sorted(repo_paths.items()):
            g = build_internals(p, name)
            internal_content[name] = {
                "cycles": [list(c) for c in g.cycles],
                "coverage": {
                    "complete": g.coverage.complete,
                    "parse_errors": list(g.coverage.parse_errors),
                    "dynamic_imports": [{"file": fpath, "line": ln} for fpath, ln in g.coverage.dynamic_imports],
                },
            }
            if crit.max_cycles is not None and len(g.cycles) > crit.max_cycles:
                findings.append({
                    "rule": "max_cycles",
                    "detail": f"{name}: {len(g.cycles)} internal module cycle(s) "
                              f"exceed the ceiling of {crit.max_cycles}",
                    "edge": None, "evidence": None})

    # require_unmatched is a criterion-quality gap (UNVERIFIABLE), not a confirmed breach
    real_violations = any(f["rule"] != "require_unmatched" for f in findings)

    # criterion-quality warnings: layers that name no repo
    unmatched = [layer for layer in crit.layers
                 if not any(n == layer or n.startswith(layer + "/") or n.endswith("/" + layer)
                            for n in names)]
    for layer in unmatched:
        findings.append({"rule": "layer", "detail": f"layer '{layer}' matches no repo",
                         "edge": None, "evidence": None})

    # a confirmed breach outranks an unverifiable criterion
    if real_violations:
        verdict = "DRIFT"
    elif unmatched or any(f["rule"] == "require_unmatched" for f in findings):
        verdict = "UNVERIFIABLE"
    else:
        verdict = "MATCH"

    criterion_doc = {"layers": list(crit.layers),
                     "forbid": [{"from": f.from_glob, "to": f.to_glob} for f in crit.forbid],
                     "max_cycles": crit.max_cycles, "owns": [list(o) for o in crit.owns]}
    if crit.require:  # keep empty-require criteria byte-identical to 2.1.0 (hash stability)
        criterion_doc["require"] = [{"from": r.from_glob, "to": r.to_glob} for r in crit.require]
    content = pack if internal_content is None else {"pack": pack, "internals": internal_content}
    coverage_doc = None
    if internal_content is not None:
        incomplete = {n: internal_content[n]["coverage"] for n in internal_content
                      if not internal_content[n]["coverage"]["complete"]}
        coverage_doc = {"complete": not incomplete, "unverifiable_repos": incomplete}
    recheck = (f"index check --root {args.root}"
               + (" --internals" if args.internals else "") + fresh_flag)
    cert = build_certificate("check", content=content, criterion=criterion_doc,
                             verdict=verdict, findings=findings, recheck=recheck,
                             tool_version=__version__, coverage=coverage_doc,
                             freshness=fresh_stamp)
    return _emit_cert(cert, args.json)


def _cmd_snapshot(args) -> int:
    from .context.pack import to_json
    from .drift import snapshot_pack, dumps_canonical
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    graph = build_graph(_repo_paths(root))
    snap = snapshot_pack(to_json(graph))
    args.out.write_text(dumps_canonical(snap), encoding="utf-8")
    print(f"wrote {args.out} repos={len(snap['repos'])} edges={len(snap['edges'])}")
    return 0


def _cmd_drift(args) -> int:
    from .drift import load_snapshot, diff_snapshots
    old = load_snapshot(args.from_snap.read_text(encoding="utf-8"))
    new = load_snapshot(args.to_snap.read_text(encoding="utf-8"))
    try:
        report = diff_snapshots(old, new)
    except ValueError as exc:
        raise SystemExit(f"drift: {exc}")
    if args.json:
        print(json.dumps(report.to_json(), indent=2))
    else:
        print(f"verdict={report.verdict}")
        for e in report.edges_added:
            print(f"  edge added: {e}")
        for e in report.edges_removed:
            print(f"  edge removed: {e}")
    return 0 if report.verdict == "MATCH" else 1


def _cmd_router(args) -> int:
    from .knowledge.atlas import build_router_pack
    from .knowledge.docs import discover_docs
    from .router import render_router
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    repo_paths = _repo_paths(root)

    def _rel(p: Path) -> str:
        r = p.resolve().relative_to(root).as_posix()
        return "" if r == "." else r

    repo_dirs = {name: _rel(p) for name, p in repo_paths.items()}
    pack = build_router_pack(build_graph(repo_paths), discover_docs(root), repo_dirs)
    text = render_router(pack)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def _cmd_verify(args) -> int:
    from .context.pack import to_json
    from .verify import build_verification
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    if (args.depends is None) == (args.exists is None):
        raise SystemExit("verify: pass exactly one of --depends 'A -> B' or --exists NAME")
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
    pack = to_json(build_graph(_repo_paths(root)))
    rec = build_verification(pack, claim, tool_version=__version__, recheck=recheck)
    if args.json:
        print(json.dumps(rec, indent=2, sort_keys=True))
    else:
        loc = f" ({rec['evidence']})" if rec["evidence"] else ""
        print(f"verdict={rec['verdict']}: {rec['detail']}{loc}")
    return {"MATCH": 0, "REFUTED": 1, "UNVERIFIABLE": 2}[rec["verdict"]]


def _cmd_freshness(args) -> int:
    from .freshness import REPORT_SCHEMA, compare_freshness, workspace_fingerprint
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    try:
        cert = json.loads(args.cert.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"freshness: cannot read certificate {args.cert}: {exc}")
    stamp = cert.get("freshness") if isinstance(cert, dict) else None
    if not stamp:
        report = {"schema": REPORT_SCHEMA, "verdict": "UNVERIFIABLE",
                  "detail": "certificate carries no freshness stamp "
                            "(mint it with index check --freshness)"}
    else:
        try:
            report = compare_freshness(stamp, workspace_fingerprint(_repo_paths(root)))
        except ValueError as exc:
            report = {"schema": REPORT_SCHEMA, "verdict": "UNVERIFIABLE", "detail": str(exc)}
    report["recheck"] = f'index freshness --cert "{args.cert}" --root "{args.root}"'
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


def _cmd_bench(args) -> int:
    from .bench import bench_workspace
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    report = bench_workspace(_repo_paths(root))
    report["recheck"] = f"index bench --root {args.root}"
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        st, pk = report["source_bytes"], report["pack_bytes"]
        red = report["reduction"]
        red_txt = f"  {red}x smaller" if red else ""
        print("token economy: index's structural pack vs the source it reads")
        print(f"  source read   {st:>11,} bytes  (~{report['approx_tokens_source']:,} tokens)  "
              f"{report['source_files']} files in {report['repos']} repos")
        print(f"  index pack    {pk:>11,} bytes  (~{report['approx_tokens_pack']:,} tokens){red_txt}")
        print(f"  note: ~{report['bytes_per_token']} bytes/token is an approximation; the reduction "
              "ratio does not depend on it.")
        print("        the pack answers structural questions (depends-on, roles, cycles); reading the "
              "code is still needed for behavior.")
    return 0


def _cmd_mcp(args) -> int:
    from .mcp import serve
    return serve()


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
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "demo":
        return cmd_demo(args)
    if args.cmd == "atlas":
        return _cmd_atlas(args)
    if args.cmd == "graph":
        return _cmd_graph(args)
    if args.cmd == "context":
        return _cmd_context(args)
    if args.cmd == "context-envelope":
        return _cmd_context_envelope(args)
    if args.cmd == "select":
        return cmd_select(args)
    if args.cmd == "viz":
        return _cmd_viz(args)
    if args.cmd == "internals":
        return _cmd_internals(args)
    if args.cmd == "check":
        return _cmd_check(args)
    if args.cmd == "snapshot":
        return _cmd_snapshot(args)
    if args.cmd == "drift":
        return _cmd_drift(args)
    if args.cmd == "router":
        return _cmd_router(args)
    if args.cmd == "verify":
        return _cmd_verify(args)
    if args.cmd == "freshness":
        return _cmd_freshness(args)
    if args.cmd == "bench":
        return _cmd_bench(args)
    if args.cmd == "mcp":
        return _cmd_mcp(args)
    return _cmd_map(args)


if __name__ == "__main__":
    raise SystemExit(main())
