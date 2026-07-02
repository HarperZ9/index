"""Symbol-level intelligence: a re-checkable, deterministic call/reference graph.

Extends the module-import graph down to functions, classes, and methods. Within
a module, calls resolve exactly via AST (high confidence). Across modules, an
imported name that binds to a real definition resolves best-effort (moderate);
anything the static scan cannot bind is surfaced honestly as unresolved, never
guessed. The graph seals with the same MATCH/DRIFT/UNVERIFIABLE certificate the
module graph uses.
"""
from __future__ import annotations

from .model import (SymbolCall, SymbolCoverage, SymbolDefinition, SymbolGraph)
from .build import (build_symbol_graph, symbol_graph_to_claims,
                    symbol_graph_to_payload)

__all__ = [
    "SymbolCall", "SymbolCoverage", "SymbolDefinition", "SymbolGraph",
    "build_symbol_graph", "symbol_graph_to_claims", "symbol_graph_to_payload",
]
