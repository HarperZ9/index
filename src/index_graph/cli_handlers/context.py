"""Context handlers: context pack and budgeted context envelope."""

from __future__ import annotations

import json

from ..context.focus import FocusRejection, focus_rejection, render_rejection
from ..context.pack import closure, focus_subgraph, preservation, render_text, to_json
from ..graph.build import build_graph
from ._common import repo_paths


def cmd_context(args) -> int:
    if args.hops is not None and args.hops < 0:
        raise SystemExit("--hops must be >= 0")
    graph = build_graph(repo_paths(args.root.resolve()))
    names = {n.name for n in graph.repos}
    if args.audit:
        return _context_audit(graph)
    preserved = None
    if args.focus:
        if args.focus not in names:
            receipt = focus_rejection(args.focus, names)
            print(
                json.dumps(receipt, indent=2, sort_keys=True)
                if args.json
                else render_rejection(receipt)
            )
            return 2
        keep = closure(list(graph.edges), args.focus, hops=args.hops)
        preserved = preservation(list(graph.edges), keep, args.focus, args.hops)
        graph = focus_subgraph(graph, keep)
        title = f"focus={args.focus}" + (
            f" hops={args.hops}" if args.hops is not None else ""
        )
    else:
        title = "workstation context"
    return _context_emit(args, graph, title, preserved)


def _context_audit(graph) -> int:
    data = to_json(graph)
    print(f"salience-faithfulness warnings: {len(data['salience_audit'])}")
    for w in data["salience_audit"]:
        print(f"  [{w['kind']}] {w['node']} (in={w['in_degree']}): {w['note']}")
    return 0


def _context_emit(args, graph, title, preserved) -> int:
    if args.json:
        pack = to_json(graph)
        if preserved is not None:
            pack["preserved"] = preserved
        print(json.dumps(pack, indent=2, sort_keys=True))
    else:
        text = render_text(graph, title)
        if preserved is not None:
            b = preserved["boundary"]
            text += (
                f"\n## Preserved\n- focus: {', '.join(preserved['focus'])}; "
                f"hops: {preserved['hops']}; kept: {preserved['kept_nodes']} nodes\n"
                f"- boundary dropped: {len(b['dropped_edges'])} edge(s) to "
                f"{len(b['dropped_nodes'])} node(s)"
            )
        print(text)
    return 0


def cmd_context_envelope(args) -> int:
    if args.budget < 1:
        raise SystemExit("--budget must be a positive integer")
    if args.hops is not None and args.hops < 0:
        raise SystemExit("--hops must be >= 0")
    from ..context.envelope import build_context_envelope

    graph = build_graph(repo_paths(args.root.resolve()))
    try:
        env = build_context_envelope(
            graph,
            root=args.root.resolve(),
            token_budget=args.budget,
            focus=args.focus,
            hops=args.hops,
        )
    except FocusRejection as exc:
        print(
            json.dumps(exc.receipt, indent=2, sort_keys=True)
            if args.json
            else render_rejection(exc.receipt)
        )
        return 2
    except ValueError as exc:
        print(str(exc))
        return 2
    if args.json:
        print(json.dumps(env, indent=2, sort_keys=True))
    else:
        print(
            f"context-envelope verdict={env['verification_verdict']} "
            f"tokens={env['budget']['approx_tokens']}/{env['budget']['token_budget']}"
        )
        print(f"retained={len(env['retained'])} omitted={len(env['omitted'])}")
    return 0


def cmd_lens(args) -> int:
    if args.budget < 1:
        raise SystemExit("--budget must be a positive integer")
    if args.hops is not None and args.hops < 0:
        raise SystemExit("--hops must be >= 0")
    from ..context.lens import build_lens_pack
    from ..viz.lens_html import render_lens_html

    graph = build_graph(repo_paths(args.root.resolve()))
    try:
        lens = build_lens_pack(
            graph,
            root=args.root.resolve(),
            token_budget=args.budget,
            focus=args.focus,
            hops=args.hops,
        )
    except FocusRejection as exc:
        print(
            json.dumps(exc.receipt, indent=2, sort_keys=True)
            if args.json
            else render_rejection(exc.receipt)
        )
        return 2
    except ValueError as exc:
        print(str(exc))
        return 2
    if args.json:
        print(json.dumps(lens, indent=2, sort_keys=True))
        return 0
    out = getattr(args, "out", None)
    if out:
        from pathlib import Path

        Path(out).write_text(render_lens_html(lens), encoding="utf-8")
        env = lens["envelope"]
        print(
            f"context lens -> {out}  "
            f"(verdict={env['verification_verdict']}, "
            f"{len(env['retained'])} retained / {len(env['omitted'])} omitted "
            f"at budget {env['budget']['token_budget']})"
        )
    else:
        print(render_lens_html(lens))
    return 0
