"""Module discovery and intra-repo import extraction, per language."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from ..graph.walk import walk_files


@dataclass(frozen=True)
class ModuleNode:
    id: str
    path: str
    language: str


@dataclass(frozen=True)
class InternalEdge:
    from_id: str
    to_id: str
    evidence_file: str
    evidence_line: int | None
    raw: str


def _py_id(rel_path: str) -> str:
    # "pkg/sub/mod.py" -> "pkg/sub/mod"
    return rel_path[:-3] if rel_path.endswith(".py") else rel_path


def discover_modules(repo_root: Path) -> list[ModuleNode]:
    mods: list[ModuleNode] = []
    for py in walk_files(repo_root, suffixes=(".py",)):
        rel = py.relative_to(repo_root).as_posix()
        mods.append(ModuleNode(id=_py_id(rel), path=rel, language="python"))
    return sorted(mods, key=lambda m: m.id)


def _id_for(base: str, ids: set[str]) -> str | None:
    """Resolve a slash-path base to an internal module id (file or package)."""
    if base in ids:
        return base
    pkg = base + "/__init__"
    return pkg if pkg in ids else None


def _dotted_to_id(dotted: str, ids: set[str]) -> str | None:
    """Map a dotted module ('app.helpers') to an internal id, file or package."""
    return _id_for(dotted.replace(".", "/"), ids)


def _resolve_relative(importer_id: str, level: int, module: str | None,
                      ids: set[str]) -> str | None:
    """Resolve a relative import with a module ('from .x import y') to an id."""
    pkg_parts = importer_id.split("/")[:-1]
    up = level - 1
    if up > len(pkg_parts):
        return None
    if up:
        pkg_parts = pkg_parts[:len(pkg_parts) - up]
    target = pkg_parts + (module.split(".") if module else [])
    if not target:
        return None
    return _id_for("/".join(target), ids)


def _python_edges(repo_root: Path, ids: set[str]) -> list[InternalEdge]:
    out: list[InternalEdge] = []
    for py in walk_files(repo_root, suffixes=(".py",)):
        rel = py.relative_to(repo_root).as_posix()
        from_id = _py_id(rel)
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    tid = _dotted_to_id(a.name, ids)
                    if tid and tid != from_id:
                        out.append(InternalEdge(from_id, tid, rel, node.lineno, f"import {a.name}"))
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.module is None:
                    # "from . import sibling" / "from .. import sibling"
                    pkg_parts = from_id.split("/")[:-1]
                    up = node.level - 1
                    base = pkg_parts[:len(pkg_parts) - up] if up <= len(pkg_parts) else None
                    if base is not None:
                        for a in node.names:
                            tid = _id_for("/".join([*base, a.name]), ids)
                            if tid and tid != from_id:
                                out.append(InternalEdge(
                                    from_id, tid, rel, node.lineno,
                                    f"from {'.' * node.level} import {a.name}"))
                    continue
                if node.level and node.level > 0:
                    tid = _resolve_relative(from_id, node.level, node.module, ids)
                    raw = f"from {'.' * node.level}{node.module or ''} import ..."
                elif node.module:
                    tid = _dotted_to_id(node.module, ids)
                    raw = f"from {node.module} import ..."
                else:
                    tid = None
                    raw = ""
                if tid and tid != from_id:
                    out.append(InternalEdge(from_id, tid, rel, node.lineno, raw))
    return out


def extract_internal_edges(repo_root: Path, modules: list[ModuleNode]) -> list[InternalEdge]:
    ids = {m.id for m in modules}
    edges = _python_edges(repo_root, ids)
    return sorted(edges, key=lambda e: (e.from_id, e.to_id, e.evidence_file, e.evidence_line or 0))
