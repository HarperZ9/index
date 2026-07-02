"""Extract function/class/method definitions from Python source via AST.

Definitions are the ground truth a call site resolves against. Only Python is
AST-exact here; other languages carry no symbol-level extraction (their
module-level graph is unchanged). Every definition carries file:line so the
wiki and the verifier can point at the exact evidence.
"""
from __future__ import annotations

import ast
from pathlib import Path

from ..graph.walk import walk_files
from ..internals.modules import _strip_suffix
from .model import SymbolDefinition

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


def _kind(node: ast.AST, in_class: bool) -> str:
    if isinstance(node, ast.ClassDef):
        return "class"
    is_async = isinstance(node, ast.AsyncFunctionDef)
    if in_class:
        return "async_method" if is_async else "method"
    return "async_function" if is_async else "function"


def _collect(node: ast.AST, module_id: str, rel: str, parent_id: str | None,
             in_class: bool, out: list[SymbolDefinition]) -> None:
    """Recurse the AST body, emitting a SymbolDefinition per def/class.

    Nested functions and classes are flattened under their lexical parent id so
    a `Class::method` and a `func::inner` are both addressable and unique.
    """
    body = getattr(node, "body", [])
    for child in body:
        if isinstance(child, (*_FUNC, ast.ClassDef)):
            name = child.name
            sym_id = f"{parent_id}::{name}" if parent_id else f"{module_id}::{name}"
            out.append(SymbolDefinition(
                id=sym_id, name=name, kind=_kind(child, in_class),
                module_id=module_id, file=rel, line=child.lineno,
                parent=parent_id, is_public=not name.startswith("_")))
            _collect(child, module_id, rel, sym_id,
                     in_class=isinstance(child, ast.ClassDef), out=out)


def extract_symbol_definitions(
    repo_root: Path, ids: set[str] | None = None,
) -> tuple[list[SymbolDefinition], list[str]]:
    """Return (definitions sorted by id, parse-error file list).

    `ids` restricts extraction to known Python module ids when supplied; when
    None, every .py file is scanned.
    """
    definitions: list[SymbolDefinition] = []
    parse_errors: list[str] = []
    for py in walk_files(repo_root, suffixes=(".py",)):
        rel = py.relative_to(repo_root).as_posix()
        module_id = _strip_suffix(rel)
        if ids is not None and module_id not in ids:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8-sig"))
        except OSError:
            continue
        except (SyntaxError, ValueError):
            parse_errors.append(rel)
            continue
        _collect(tree, module_id, rel, None, in_class=False, out=definitions)
    definitions = _dedupe_last(definitions)
    definitions.sort(key=lambda d: d.id)
    parse_errors.sort()
    return definitions, parse_errors


def _dedupe_last(definitions: list[SymbolDefinition]) -> list[SymbolDefinition]:
    """Collapse same-id definitions to one, keeping the last (source order).

    A legal Python redefinition (two ``def foo`` at module scope, or a
    decorator that rebinds a name) would otherwise emit two SymbolDefinitions
    with an identical id, which silently collide in the wiki page map and make
    resolution ambiguous. Python's runtime keeps the last binding, so the static
    graph keeps the last definition site too. ``_collect`` appends in source
    order, so the later dict write wins.
    """
    by_id: dict[str, SymbolDefinition] = {}
    for d in definitions:
        by_id[d.id] = d
    return list(by_id.values())
