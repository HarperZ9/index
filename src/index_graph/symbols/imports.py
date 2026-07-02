"""Per-module import binding table: which local name maps to which module symbol.

Only `from <internal-module> import name` bindings are recorded, because only
those can be resolved to a definition inside this repo. Plain `import pkg.mod`
and external imports are not bindable to a symbol and are left out (a call
through them stays honestly unresolved).
"""
from __future__ import annotations

import ast
from pathlib import Path

from ..graph.walk import walk_files
from ..internals.modules import (_dotted_to_id, _id_for, _pkg_depth,
                                  _resolve_relative, _strip_suffix)


def _relative_target(from_id: str, level: int, module: str | None,
                     ids: set[str], depth: int) -> str | None:
    if module is None:
        return None
    return _resolve_relative(from_id, level, module, ids, depth)


def _bindings_for_module(from_id: str, tree: ast.AST, ids: set[str],
                         depth: int) -> dict[str, tuple[str, str]]:
    """Map a locally-bound name -> (target_module_id, imported_name)."""
    bindings: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level and node.level > 0:
            # relative: from .pkg import name  /  from . import name
            if node.module is None:
                pkg_parts = from_id.split("/")[:-1]
                if node.level > depth:
                    continue
                base = pkg_parts[:len(pkg_parts) - (node.level - 1)]
                for a in node.names:
                    tid = _id_for("/".join([*base, a.name]), ids)
                    if tid:
                        bindings[a.asname or a.name] = (tid, a.name)
                continue
            target_mod = _relative_target(from_id, node.level, node.module, ids, depth)
        elif node.module:
            target_mod = _dotted_to_id(node.module, ids)
        else:
            target_mod = None
        if not target_mod:
            continue
        for a in node.names:
            if a.name == "*":
                continue
            bindings[a.asname or a.name] = (target_mod, a.name)
    return bindings


def module_import_bindings(repo_root: Path, ids: set[str]) -> dict[str, dict[str, tuple[str, str]]]:
    """For each Python module id, its {local_name: (target_module_id, name)} table."""
    tables: dict[str, dict[str, tuple[str, str]]] = {}
    for py in walk_files(repo_root, suffixes=(".py",)):
        rel = py.relative_to(repo_root).as_posix()
        from_id = _strip_suffix(rel)
        if from_id not in ids:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, ValueError):
            continue
        depth = _pkg_depth(repo_root, from_id)
        tables[from_id] = _bindings_for_module(from_id, tree, ids, depth)
    return tables
