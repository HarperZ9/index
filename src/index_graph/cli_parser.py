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
    _add_select_parser(sub)
    _add_viz_parser(sub)
    _add_atlas_parser(sub)
    add_wiki_parser(sub)
    _add_internals_parser(sub)
    _add_check_parser(sub)
    _add_snapshot_parser(sub)
    _add_drift_parser(sub)
    _add_router_parser(sub)
    _add_verify_parser(sub)
    _add_freshness_parser(sub)
    _add_invalidate_parser(sub)
    _add_bench_parser(sub)
    _add_serve_parser(sub)
    sub.add_parser(
        "mcp",
        help="Serve the MCP-shaped stdio protocol face (JSON-RPC over stdin/stdout).",
    )
    return parser
