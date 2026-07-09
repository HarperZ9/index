"""Command-line entry point: map (default) + graph + context subcommands."""

from __future__ import annotations

import json
import sys
from dataclasses import replace

from . import __version__
from .cli_handlers import (
    cmd_atlas,
    cmd_workbench,
    cmd_bench,
    cmd_check,
    cmd_context,
    cmd_context_envelope,
    cmd_lens,
    cmd_drift,
    cmd_freshness,
    cmd_graph,
    cmd_internals,
    cmd_internals_symbols,
    cmd_lsp,
    cmd_mcp,
    cmd_router,
    cmd_serve,
    cmd_snapshot,
    cmd_symbols,
    cmd_verify,
    cmd_watch,
    cmd_viz,
)
from .cli_parser import build_parser
from .config import load_config
from .context.select import cmd_select
from .flagship import cmd_demo, cmd_doctor, cmd_status
from .freshness.invalidate_cli import cmd_invalidate
from .scan import build_map, write_map
from .wiki.cli import cmd_wiki

_SUBCOMMANDS = {
    "map",
    "graph",
    "context",
    "context-envelope",
    "lens",
    "select",
    "viz",
    "atlas",
    "workbench",
    "wiki",
    "internals",
    "internals-symbols",
    "symbols",
    "check",
    "snapshot",
    "drift",
    "router",
    "verify",
    "freshness",
    "watch",
    "invalidate",
    "bench",
    "serve",
    "lsp",
    "mcp",
    "status",
    "doctor",
    "demo",
}

# Dispatch table for named subcommands. `map` is intentionally absent: it is
# the implicit default reached when no known subcommand leads the invocation.
_DISPATCH = {
    "status": cmd_status,
    "doctor": cmd_doctor,
    "demo": cmd_demo,
    "atlas": cmd_atlas,
    "workbench": cmd_workbench,
    "wiki": cmd_wiki,
    "graph": cmd_graph,
    "context": cmd_context,
    "context-envelope": cmd_context_envelope,
    "lens": cmd_lens,
    "select": cmd_select,
    "viz": cmd_viz,
    "internals": cmd_internals,
    "internals-symbols": cmd_internals_symbols,
    "symbols": cmd_symbols,
    "check": cmd_check,
    "snapshot": cmd_snapshot,
    "drift": cmd_drift,
    "router": cmd_router,
    "verify": cmd_verify,
    "freshness": cmd_freshness,
    "watch": cmd_watch,
    "invalidate": cmd_invalidate,
    "bench": cmd_bench,
    "serve": cmd_serve,
    "lsp": cmd_lsp,
    "mcp": cmd_mcp,
}


def _configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


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
        if args.dry_run:
            raise SystemExit(
                "map: --dry-run applies to the file-writing mode; "
                "--json already writes nothing"
            )
        print(json.dumps(build_map(root, config, __version__).to_json(), indent=2))
        return 0
    output = args.output.resolve() if args.output else root / "INDEX.json"
    if args.dry_run:
        print(f"index map: would write {output} (dry-run, nothing written)")
        data = build_map(root, config, __version__)
        print(f"repos={data.repo_count} dirty={data.dirty_count}")
        return 0
    print(f"index map: writing {output}")
    data = write_map(root, config, __version__, output)
    print(f"wrote {output}")
    print(f"repos={data.repo_count} dirty={data.dirty_count}")
    return 0


def _normalize_argv(argv: list[str] | None) -> list[str]:
    raw = list(sys.argv[1:] if argv is None else argv)
    # No leading subcommand: route top-level --version/--help to the root
    # parser; otherwise treat the invocation as the implicit `map` command
    # (preserves v0.2.0 behavior).
    if not raw or raw[0] not in _SUBCOMMANDS:
        if raw and raw[0] in ("--version", "-h", "--help"):
            build_parser().parse_args(raw[:1])  # prints and exits
        raw = ["map", *raw]
    return raw


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(_normalize_argv(argv))
    handler = _DISPATCH.get(args.cmd, _cmd_map)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
