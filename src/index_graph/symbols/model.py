"""Frozen data model for the symbol-level call/reference graph.

A SymbolDefinition is a function/class/method the AST saw defined. A SymbolCall
is a call site, carrying file:line evidence and an honest resolution label: a
resolved edge names a real definition; an unresolved reference names only the
bare name it could not statically bind, and is never guessed into an edge.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolDefinition:
    """A function, class, or method the AST recorded as defined."""
    id: str            # "module_id::name" or "module_id::Class::method"
    name: str          # bare name (unqualified)
    kind: str          # "function" | "async_function" | "class" | "method" | "async_method"
    module_id: str     # parent module id (matches InternalGraph module ids)
    file: str          # repo-relative path
    line: int          # 1-indexed definition line
    parent: str | None  # "module_id::Class" for a method; None for a top-level symbol
    is_public: bool    # name does not start with "_"


@dataclass(frozen=True)
class SymbolCall:
    """A call or reference site, with evidence and an honest resolution label."""
    from_symbol: str        # caller symbol id
    to_symbol: str | None   # resolved target id, or None when unresolved
    to_name: str            # bare name as written at the call site
    kind: str               # "call"
    evidence_file: str      # repo-relative path
    evidence_line: int      # 1-indexed line of the call site
    raw: str                # source-line fragment
    resolution: str         # "exact" | "cross_module" | "cross_module_unresolved"
    confidence: str         # "high" | "moderate" | "low"


@dataclass(frozen=True)
class SymbolCoverage:
    """What the symbol scan could and could not statically see."""
    symbols: int
    resolved_calls: int
    unresolved_calls: int
    parse_errors: tuple[str, ...]
    dynamic_calls: tuple[tuple[str, int], ...]  # (file, line) of getattr/variable dispatch

    @property
    def complete(self) -> bool:
        return not self.parse_errors and not self.dynamic_calls


@dataclass(frozen=True)
class SymbolGraph:
    """Per-repository symbol graph, analogous to InternalGraph."""
    repo: str
    symbols: tuple[SymbolDefinition, ...]
    calls: tuple[SymbolCall, ...]
    coverage: SymbolCoverage
    fan_in: dict[str, int]   # resolved-target id -> number of distinct callers
    fan_out: dict[str, int]  # caller id -> number of distinct resolved targets
