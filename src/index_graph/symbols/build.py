"""Assemble the SymbolGraph: definitions + resolved/unresolved calls + coverage.

Deterministic by construction: definitions and calls are sorted, fan-in/out are
derived from the sorted resolved calls, and the whole graph serializes to a
canonical payload whose SHA is byte-identical across runs.
"""
from __future__ import annotations

from pathlib import Path

from ..internals.modules import discover_modules
from .calls import extract_symbol_calls
from .definitions import extract_symbol_definitions
from .imports import module_import_bindings
from .model import SymbolCall, SymbolCoverage, SymbolDefinition, SymbolGraph


def _python_ids(repo_root: Path) -> set[str]:
    return {m.id for m in discover_modules(repo_root) if m.language == "python"}


def _fan(calls: tuple[SymbolCall, ...]) -> tuple[dict[str, int], dict[str, int]]:
    fan_out: dict[str, int] = {}
    fan_in: dict[str, int] = {}
    seen_out: set[tuple[str, str]] = set()
    seen_in: set[tuple[str, str]] = set()
    for c in calls:
        if c.to_symbol is None:
            continue
        if (c.from_symbol, c.to_symbol) not in seen_out:
            seen_out.add((c.from_symbol, c.to_symbol))
            fan_out[c.from_symbol] = fan_out.get(c.from_symbol, 0) + 1
        if (c.to_symbol, c.from_symbol) not in seen_in:
            seen_in.add((c.to_symbol, c.from_symbol))
            fan_in[c.to_symbol] = fan_in.get(c.to_symbol, 0) + 1
    return fan_in, fan_out


def build_symbol_graph(repo_root: Path, repo_name: str | None = None) -> SymbolGraph:
    root = repo_root.resolve()
    name = repo_name or root.name
    ids = _python_ids(root)
    definitions, parse_errors = extract_symbol_definitions(root, ids)
    import_tables = module_import_bindings(root, ids)
    calls_list, dynamic = extract_symbol_calls(root, definitions, ids, import_tables)
    calls = tuple(calls_list)
    resolved = sum(1 for c in calls if c.to_symbol is not None)
    coverage = SymbolCoverage(
        symbols=len(definitions),
        resolved_calls=resolved,
        unresolved_calls=len(calls) - resolved,
        parse_errors=tuple(parse_errors),
        dynamic_calls=tuple(dynamic),
    )
    fan_in, fan_out = _fan(calls)
    return SymbolGraph(repo=name, symbols=tuple(definitions), calls=calls,
                       coverage=coverage, fan_in=fan_in, fan_out=fan_out)


def _definition_payload(d: SymbolDefinition) -> dict:
    return {"id": d.id, "name": d.name, "kind": d.kind, "module_id": d.module_id,
            "file": d.file, "line": d.line, "parent": d.parent, "is_public": d.is_public}


def _call_payload(c: SymbolCall) -> dict:
    return {"from_symbol": c.from_symbol, "to_symbol": c.to_symbol, "to_name": c.to_name,
            "kind": c.kind, "file": c.evidence_file, "line": c.evidence_line,
            "raw": c.raw, "resolution": c.resolution, "confidence": c.confidence}


def symbol_graph_to_payload(g: SymbolGraph) -> dict:
    """A canonical, JSON-serializable projection for hashing, CLI, and MCP."""
    return {
        "repo": g.repo,
        "symbols": [_definition_payload(d) for d in g.symbols],
        "calls": [_call_payload(c) for c in g.calls],
        "fan_in": dict(sorted(g.fan_in.items())),
        "fan_out": dict(sorted(g.fan_out.items())),
        "coverage": {
            "complete": g.coverage.complete,
            "symbols": g.coverage.symbols,
            "resolved_calls": g.coverage.resolved_calls,
            "unresolved_calls": g.coverage.unresolved_calls,
            "parse_errors": list(g.coverage.parse_errors),
            "dynamic_calls": [{"file": f, "line": ln} for f, ln in g.coverage.dynamic_calls],
        },
    }


def symbol_graph_to_claims(g: SymbolGraph) -> set[tuple[str, str]]:
    """The set of resolved (caller, callee) edges the wiki may claim and the
    verifier re-derives. Only edges with a real resolved target are claimable;
    an unresolved reference is never a claimable edge."""
    return {(c.from_symbol, c.to_symbol) for c in g.calls if c.to_symbol is not None}
