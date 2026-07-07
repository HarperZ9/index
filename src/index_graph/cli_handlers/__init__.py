"""Per-subcommand handler functions for the `index` CLI.

Split out of the former monolithic ``cli.py`` so every module stays under
the 300-line ceiling and every handler under 50 lines. Behavior is identical
to the pre-split single-file implementation.
"""

from __future__ import annotations

from .certify import cmd_check, cmd_drift, cmd_snapshot
from .context import cmd_context, cmd_context_envelope, cmd_lens
from .graph import cmd_graph, cmd_internals, cmd_internals_symbols, cmd_viz
from .lsp import cmd_lsp
from .maps import cmd_atlas, cmd_router
from .serve import cmd_serve
from .symbols import cmd_symbols
from .verify import cmd_bench, cmd_freshness, cmd_mcp, cmd_verify

__all__ = [
    "cmd_atlas",
    "cmd_bench",
    "cmd_check",
    "cmd_context",
    "cmd_context_envelope",
    "cmd_lens",
    "cmd_drift",
    "cmd_freshness",
    "cmd_graph",
    "cmd_internals",
    "cmd_internals_symbols",
    "cmd_lsp",
    "cmd_mcp",
    "cmd_router",
    "cmd_serve",
    "cmd_snapshot",
    "cmd_symbols",
    "cmd_verify",
    "cmd_viz",
]
