"""Argument-parser construction for the `index` CLI.

``build_parser`` orchestrates per-subcommand builder helpers so no single
function exceeds the 50-line ceiling. The set of subcommands, flags, and
help text is identical to the pre-split single-file parser.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .wiki.cli import add_wiki_parser


def _add_map_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="report the write path and repo counts without writing anything",
    )
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--jobs", type=int, default=None)


def _add_telos_parser(sub, name: str, help_text: str) -> None:
    p = sub.add_parser(name, help=help_text)
    p.add_argument(
        "--json", action="store_true", help="emit a Project Telos action envelope"
    )


def _add_graph_parser(sub) -> None:
    g = sub.add_parser("graph", help="Derive the repo-level dependency graph.")
    g.add_argument("--root", type=Path, default=Path.cwd())
    g.add_argument("--json", action="store_true")
    g.add_argument(
        "--cycles",
        action="store_true",
        help="Report dependency cycles instead of the full graph.",
    )


def _add_context_parser(sub) -> None:
    c = sub.add_parser("context", help="Render the synthesis context pack.")
    c.add_argument("--root", type=Path, default=Path.cwd())
    c.add_argument("--json", action="store_true")
    c.add_argument("--focus", default=None)
    c.add_argument("--hops", type=int, default=None)
    c.add_argument("--audit", action="store_true")


def _add_context_envelope_parser(sub) -> None:
    ce = sub.add_parser(
        "context-envelope",
        help="Emit a budgeted, receipt-backed context envelope.",
    )
    ce.add_argument("--root", type=Path, default=Path.cwd())
    ce.add_argument(
        "--budget",
        type=int,
        default=1200,
        help="approximate token budget for retained context entries",
    )
    ce.add_argument("--focus", default=None)
    ce.add_argument("--hops", type=int, default=None)
    ce.add_argument("--json", action="store_true")
    ce.add_argument(
        "--verify",
        type=Path,
        default=None,
        metavar="ENVELOPE_JSON",
        help="re-derive a saved envelope's freshness against the current workspace "
             "(exit 0 if still fresh, 1 if it drifted); other build flags are ignored",
    )


def _add_lens_parser(sub) -> None:
    ln = sub.add_parser(
        "lens",
        help="Render the Context Lens: a live, self-contained page showing "
             "what a token budget retains and drops, with failure codes.",
    )
    ln.add_argument("--root", type=Path, default=Path.cwd())
    ln.add_argument(
        "--budget",
        type=int,
        default=1200,
        help="approximate token budget the lens opens at (slider varies it live)",
    )
    ln.add_argument("--focus", default=None)
    ln.add_argument("--hops", type=int, default=None)
    ln.add_argument("--out", default=None, help="write the HTML here instead of stdout")
    ln.add_argument("--json", action="store_true", help="emit the lens pack JSON instead of HTML")


def _add_workbench_parser(sub) -> None:
    wbp = sub.add_parser(
        "workbench",
        help="Render the unified workbench: map, docs, context lens, health, "
             "and the flagship spine in one self-contained page.",
    )
    wbp.add_argument("--root", type=Path, default=Path.cwd())
    wbp.add_argument("--budget", type=int, default=6000,
                     help="token budget the context lens opens at")
    wbp.add_argument("--max-doc-bodies", type=int, default=200,
                     help="rendered doc bodies embedded in the page (page-weight budget; the doc list and search always cover all docs)")
    wbp.add_argument("--spine-dir", default=None,
                     help="directory of captured flagship-action envelopes (*.json)")
    wbp.add_argument("--out", default=None, help="write the HTML here instead of stdout")
    wbp.add_argument("--json", action="store_true",
                     help="emit the workbench pack JSON (minus svg) instead of HTML")


def _add_watch_parser(sub) -> None:
    w = sub.add_parser(
        "watch",
        help="Auto-resync on file change: hold the prior fingerprint, emit a "
             "live FRESH/STALE receipt per change, optionally regenerate an artifact.",
    )
    w.add_argument("--root", type=Path, default=Path.cwd())
    w.add_argument("--interval", type=float, default=2.0,
                   help="poll seconds (latency floor; the fingerprint is authoritative)")
    w.add_argument("--max-ticks", type=int, default=0,
                   help="stop after N ticks (0 = run until Ctrl-C)")
    w.add_argument("--regen", choices=["workbench", "atlas"], default=None,
                   help="regenerate this artifact on every detected change")
    w.add_argument("--out", default=None, help="artifact output path for --regen")
    w.add_argument("--json", action="store_true",
                   help="emit one freshness-sync receipt (JSON) per line")


def _add_select_parser(sub) -> None:
    se = sub.add_parser(
        "select",
        help="Select files under a root; every rejection carries a typed receipt.",
    )
    se.add_argument("--root", type=Path, default=Path.cwd())
    se.add_argument(
        "--suffix",
        dest="suffixes",
        action="append",
        default=None,
        help="keep only files with this suffix (repeatable, e.g. --suffix .md)",
    )
    se.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="file budget; paths beyond it get over-budget receipts",
    )
    se.add_argument("--json", action="store_true")


def _add_viz_parser(sub) -> None:
    v = sub.add_parser("viz", help="Render the dependency graph (html/svg/mermaid).")
    v.add_argument("--root", type=Path, default=Path.cwd())
    v.add_argument(
        "--format", choices=["html", "svg", "mermaid", "all"], default="html"
    )
    v.add_argument("--focus", default=None)
    v.add_argument("--no-external", action="store_true")
    v.add_argument("--out", default=None)
    v.add_argument("--out-dir", default=None)


def _add_atlas_parser(sub) -> None:
    a = sub.add_parser("atlas", help="Two-layer code + knowledge map (repos + docs).")
    a.add_argument("--root", type=Path, default=Path.cwd())
    a.add_argument("--json", action="store_true")
    a.add_argument("--format", choices=["html"], default=None)
    a.add_argument("--out", default=None)
    a.add_argument("--no-external", action="store_true")


def _add_internals_parser(sub) -> None:
    i = sub.add_parser("internals", help="Intra-repo module dependency graph.")
    i.add_argument("--root", type=Path, default=Path.cwd())
    i.add_argument("--json", action="store_true")
    i.add_argument("--cycles", action="store_true")


def _add_internals_symbols_parser(sub) -> None:
    s = sub.add_parser(
        "internals-symbols",
        help="Symbol-level call/reference graph for one repo (Python AST-exact "
        "within-module; best-effort, honestly-labeled cross-module).",
    )
    s.add_argument("--root", type=Path, default=Path.cwd())
    s.add_argument("--json", action="store_true")
    s.add_argument(
        "--coverage",
        action="store_true",
        help="Report only the coverage summary (symbols, resolved/unresolved "
        "calls, parse errors, dynamic dispatch).",
    )


def _add_symbols_parser(sub) -> None:
    s = sub.add_parser(
        "symbols",
        help="Navigate the symbol graph: go-to-definition, find-references, and "
        "find-implementations for a symbol, each hop with file:line evidence.",
    )
    s.add_argument(
        "query",
        help="symbol id (module::name or Class::method) or a bare name",
    )
    s.add_argument("--root", type=Path, default=Path.cwd())
    s.add_argument("--json", action="store_true")
    s.add_argument(
        "--def", dest="definition", action="store_true",
        help="Only go-to-definition (matching definitions with file:line).",
    )
    s.add_argument(
        "--refs", dest="references", action="store_true",
        help="Only find-references (resolved callers; unresolved refs listed "
        "separately, never as callers).",
    )
    s.add_argument(
        "--impls", dest="implementations", action="store_true",
        help="Only find-implementations (in-repo subclasses of a class or "
        "overrides of a method). No flag reports all three sections.",
    )


def _add_check_parser(sub) -> None:
    ck = sub.add_parser(
        "check",
        help="Check structure against the declared [architecture] criterion.",
    )
    ck.add_argument("--root", type=Path, default=Path.cwd())
    ck.add_argument(
        "--internals", action="store_true", help="Include intra-repo module checks."
    )
    ck.add_argument(
        "--freshness",
        action="store_true",
        help="Stamp the certificate with a workspace content fingerprint.",
    )
    ck.add_argument("--json", action="store_true")
    ck.add_argument("--config", type=Path, default=None)


def _add_snapshot_parser(sub) -> None:
    sn = sub.add_parser(
        "snapshot", help="Write a canonical graph snapshot for drift diffing."
    )
    sn.add_argument("--root", type=Path, default=Path.cwd())
    sn.add_argument("--out", type=Path, required=True)


def _add_drift_parser(sub) -> None:
    dr = sub.add_parser("drift", help="Diff two snapshots into a drift report.")
    dr.add_argument("--from", dest="from_snap", type=Path, required=True)
    dr.add_argument("--to", dest="to_snap", type=Path, required=True)
    dr.add_argument("--json", action="store_true")


def _add_router_parser(sub) -> None:
    rt = sub.add_parser(
        "router",
        help="Emit a workspace map (CLAUDE.md/AGENTS.md) from the graph and docs.",
    )
    rt.add_argument("--root", type=Path, default=Path.cwd())
    rt.add_argument("--out", default=None)
    rt.add_argument("--max-docs", type=int, default=500,
                    help="maximum doc-to-repo edges rendered in the router markdown")
    rt.add_argument("--no-cache", action="store_true",
                    help="disable the workspace-router filesystem cache for this run")


def _add_verify_parser(sub) -> None:
    vf = sub.add_parser(
        "verify",
        help="Ground a structural claim against the graph "
        "(MATCH/REFUTED/UNVERIFIABLE).",
    )
    vf.add_argument("--root", type=Path, default=Path.cwd())
    vf.add_argument("--depends", default=None, help="claim 'A -> B' (A depends on B)")
    vf.add_argument("--exists", default=None, help="claim that repo NAME exists")
    vf.add_argument("--json", action="store_true")


def _add_freshness_parser(sub) -> None:
    fr = sub.add_parser(
        "freshness",
        help="Has the workspace changed since a certificate was minted? (FRESH/STALE).",
    )
    fr.add_argument(
        "--cert",
        type=Path,
        required=True,
        help="A certificate JSON carrying a freshness stamp (index check --freshness).",
    )
    fr.add_argument("--root", type=Path, default=Path.cwd())
    fr.add_argument("--json", action="store_true")


def _add_invalidate_parser(sub) -> None:
    inv = sub.add_parser(
        "invalidate",
        help="Diff the tree against a pinned fingerprint and name "
        "exactly what the changes invalidate (FRESH/STALE).",
    )
    inv.add_argument("--root", type=Path, default=Path.cwd())
    inv.add_argument(
        "--pin",
        type=Path,
        default=None,
        help="A pin JSON minted earlier with --out; emits the "
        "index.invalidation/1 report against it.",
    )
    inv.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Mint a pin of the current tree to this file.",
    )
    inv.add_argument("--json", action="store_true")


def _add_bench_parser(sub) -> None:
    bn = sub.add_parser(
        "bench",
        help="Token economy: index's structural pack vs reading the source "
        "it distills.",
    )
    bn.add_argument("--root", type=Path, default=Path.cwd())
    bn.add_argument("--json", action="store_true")
    bn.add_argument("--no-cache", action="store_true",
                    help="disable the workspace bench filesystem cache for this run")


def _add_serve_parser(sub) -> None:
    sv = sub.add_parser(
        "serve",
        help="Local http.server that derives a repo's verified wiki on demand "
        "from its forge path (consent-clean; robots.txt disallows indexing).",
    )
    sv.add_argument(
        "--host",
        default="127.0.0.1",
        help="interface to bind (default 127.0.0.1, loopback only)",
    )
    sv.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port to bind (default 8000; 0 picks an ephemeral port)",
    )


def _add_lsp_parser(sub) -> None:
    lsp = sub.add_parser(
        "lsp",
        help="Start a stdio LSP server exposing go-to-definition and "
        "find-references over the symbol graph (VSCode/Neovim/JetBrains). "
        "Answers are evidence-backed file:line or honestly empty; a stale "
        "workspace is detected, never silently answered.",
    )
    lsp.add_argument("--root", type=Path, default=Path.cwd())
    lsp.add_argument(
        "--trace",
        choices=["off", "messages", "verbose"],
        default="off",
        help="LSP trace verbosity (reserved; currently a no-op placeholder).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="index",
        description="Repository inventory maps + dependency graph + context packs.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="cmd")

    _add_telos_parser(sub, "status", "emit Index's Project Telos operator-spine status")
    _add_telos_parser(sub, "doctor", "check Index's operator-spine readiness")
    _add_telos_parser(sub, "demo", "show Index's operator-spine demo command")
    _add_map_args(
        sub.add_parser("map", help="Write the repository inventory map (default).")
    )
    _add_graph_parser(sub)
    _add_context_parser(sub)
    _add_context_envelope_parser(sub)
    _add_watch_parser(sub)
    _add_lens_parser(sub)
    _add_select_parser(sub)
    _add_viz_parser(sub)
    _add_atlas_parser(sub)
    _add_workbench_parser(sub)
    add_wiki_parser(sub)
    _add_internals_parser(sub)
    _add_internals_symbols_parser(sub)
    _add_symbols_parser(sub)
    _add_check_parser(sub)
    _add_snapshot_parser(sub)
    _add_drift_parser(sub)
    _add_router_parser(sub)
    _add_verify_parser(sub)
    _add_freshness_parser(sub)
    _add_invalidate_parser(sub)
    _add_bench_parser(sub)
    _add_serve_parser(sub)
    _add_lsp_parser(sub)
    sub.add_parser(
        "mcp",
        help="Serve the MCP-shaped stdio protocol face (JSON-RPC over stdin/stdout).",
    )
    return parser
