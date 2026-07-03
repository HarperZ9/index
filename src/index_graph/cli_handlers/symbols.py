"""Handler for `index symbols <query>`: symbol-granular navigation.

Go-to-definition, find-references, and find-implementations over the wave-1
symbol graph, each hop carrying file:line evidence. The query is a symbol id
(``module::name`` or ``Class::method``) or a bare name. With no mode flag, all
three sections are reported; ``--def`` / ``--refs`` / ``--impls`` select one.

Every row defers to the graph's own resolution, so nothing is guessed: an
unresolved reference is listed separately and never as a caller, and an
external base class yields no implementation edge.
"""
from __future__ import annotations

import json

from ..symbols import (build_symbol_navigator, find_definitions,
                       find_implementations, find_references)
from ._common import require_dir


def cmd_symbols(args) -> int:
    root = require_dir(args.root)
    query = args.query.strip()
    graph, edges = build_symbol_navigator(root)
    want_def, want_refs, want_impls = _modes(args)

    result: dict = {"repo": graph.repo, "query": query}
    if want_def:
        result["definitions"] = find_definitions(graph, query)
    if want_refs:
        result["references"] = find_references(graph, query)
    if want_impls:
        result["implementations"] = find_implementations(graph, edges, query)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    _render_text(result, want_def, want_refs, want_impls)
    return _exit_code(result, want_def, want_refs, want_impls)


def _modes(args) -> tuple[bool, bool, bool]:
    """Selected sections; no flag means all three."""
    d, r, i = args.definition, args.references, args.implementations
    if not (d or r or i):
        return True, True, True
    return d, r, i


def _exit_code(result: dict, want_def, want_refs, want_impls) -> int:
    """0 when the query matched something; 2 when every requested section was empty.

    A non-zero code lets scripts distinguish "no such symbol / no evidence" from
    a successful lookup, without ever fabricating a match.
    """
    found = False
    if want_def:
        found = found or bool(result["definitions"])
    if want_refs:
        refs = result["references"]
        found = found or bool(refs["references"]) or bool(refs["unresolved"])
    if want_impls:
        impls = result["implementations"]
        found = found or bool(impls["subclasses"]) or bool(impls["overrides"])
    return 0 if found else 2


def _render_text(result: dict, want_def, want_refs, want_impls) -> None:
    print(f"symbol query: {result['query']}  (repo {result['repo']})")
    if want_def:
        _render_definitions(result["definitions"])
    if want_refs:
        _render_references(result["references"])
    if want_impls:
        _render_implementations(result["implementations"])


def _render_definitions(defs: list) -> None:
    print(f"definitions ({len(defs)}):")
    if not defs:
        print("  (none: no matching definition in this repo)")
    for d in defs:
        vis = "public" if d["is_public"] else "internal"
        print(f"  {d['id']}  [{d['kind']}, {vis}]  {d['file']}:{d['line']}")


def _render_references(refs: dict) -> None:
    resolved = refs["references"]
    unresolved = refs["unresolved"]
    print(f"references ({len(resolved)} resolved, {len(unresolved)} unresolved):")
    for r in resolved:
        print(f"  {r['from_symbol']}  {r['file']}:{r['line']}  "
              f"[{r['resolution']}, {r['confidence']}]")
    for u in unresolved:
        print(f"  ? {u['from_symbol']}  {u['file']}:{u['line']}  "
              f"(unresolved same-name reference, never a caller)")


def _render_implementations(impls: dict) -> None:
    subs = impls["subclasses"]
    overs = impls["overrides"]
    print(f"implementations ({len(subs)} subclasses, {len(overs)} overrides):")
    for s in subs:
        print(f"  subclass {s['child']}  {s['file']}:{s['line']}  [{s['resolution']}]")
    for o in overs:
        print(f"  override {o['child']}  {o['file']}:{o['line']}  [{o['resolution']}]")
