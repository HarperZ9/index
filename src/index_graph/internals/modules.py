"""Module discovery and intra-repo import extraction, per language.

Python is AST-exact. JavaScript/TypeScript, Rust, and Go are best-effort and
file-level: relative or path-aligned imports resolve to sibling modules, bare
or external specifiers are ignored. Dynamic and aliased imports may be missed.
"""
from __future__ import annotations

import ast
import re
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


_LANG_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "javascript", ".tsx": "javascript",
    ".rs": "rust", ".go": "go",
}
_SUFFIXES = tuple(_LANG_BY_SUFFIX)


def _strip_suffix(rel: str) -> str:
    dot = rel.rfind(".")
    slash = rel.rfind("/")
    return rel[:dot] if dot > slash else rel


def discover_modules(repo_root: Path) -> list[ModuleNode]:
    mods: list[ModuleNode] = []
    for f in walk_files(repo_root, suffixes=_SUFFIXES):
        rel = f.relative_to(repo_root).as_posix()
        lang = _LANG_BY_SUFFIX.get(f.suffix, "")
        if not lang:
            continue
        mods.append(ModuleNode(id=_strip_suffix(rel), path=rel, language=lang))
    return sorted(mods, key=lambda m: m.id)


# --- Python (AST-exact) ----------------------------------------------------

def _id_for(base: str, ids: set[str]) -> str | None:
    """Resolve a slash-path base to an internal module id (file or package)."""
    if base in ids:
        return base
    pkg = base + "/__init__"
    return pkg if pkg in ids else None


def _dotted_to_id(dotted: str, ids: set[str]) -> str | None:
    return _id_for(dotted.replace(".", "/"), ids)


def _resolve_relative(importer_id: str, level: int, module: str | None,
                      ids: set[str]) -> str | None:
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
        from_id = _strip_suffix(rel)
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


# --- JavaScript / TypeScript (best-effort, relative specifiers) ------------

_JS_IMPORT = re.compile(
    r"""(?:import|export)[^'"]*?from\s*['"]([^'"]+)['"]"""
    r"""|require\(\s*['"]([^'"]+)['"]\s*\)"""
    r"""|import\(\s*['"]([^'"]+)['"]\s*\)""")
_JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")


def _js_resolve(importer_rel: str, spec: str, ids: set[str]) -> str | None:
    if not spec.startswith("."):
        return None
    base = (Path(importer_rel).parent / spec).as_posix()
    parts: list[str] = []
    for seg in base.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    cand = "/".join(parts)
    if "." in Path(cand).name:
        cand = _strip_suffix(cand)
    if cand in ids:
        return cand
    idx = cand + "/index"
    return idx if idx in ids else None


def _js_edges(repo_root: Path, ids: set[str]) -> list[InternalEdge]:
    out: list[InternalEdge] = []
    for f in walk_files(repo_root, suffixes=_JS_SUFFIXES):
        rel = f.relative_to(repo_root).as_posix()
        from_id = _strip_suffix(rel)
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for m in _JS_IMPORT.finditer(line):
                spec = m.group(1) or m.group(2) or m.group(3)
                if not spec:
                    continue
                tid = _js_resolve(rel, spec, ids)
                if tid and tid != from_id:
                    out.append(InternalEdge(from_id, tid, rel, i, line.strip()))
    return out


# --- Rust (best-effort, mod declarations) ----------------------------------

_RUST_MOD = re.compile(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;")


def _rust_edges(repo_root: Path, ids: set[str]) -> list[InternalEdge]:
    out: list[InternalEdge] = []
    for f in walk_files(repo_root, suffixes=(".rs",)):
        rel = f.relative_to(repo_root).as_posix()
        from_id = _strip_suffix(rel)
        parent = Path(rel).parent.as_posix()
        parent = "" if parent == "." else parent + "/"
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = _RUST_MOD.match(line)
            if not m:
                continue
            name = m.group(1)
            for cand in (f"{parent}{name}", f"{parent}{name}/mod", f"{from_id}/{name}"):
                if cand in ids and cand != from_id:
                    out.append(InternalEdge(from_id, cand, rel, i, line.strip()))
                    break
    return out


# --- Go (best-effort, internal package imports) ----------------------------

_GO_MODULE = re.compile(r"^\s*module\s+(\S+)")
_GO_IMPORT_SINGLE = re.compile(r'^\s*import\s+"([^"]+)"')
_GO_IMPORT_BLOCK_LINE = re.compile(r'^\s*"([^"]+)"')


def _go_module_path(repo_root: Path) -> str | None:
    gomod = repo_root / "go.mod"
    if not gomod.is_file():
        return None
    try:
        for line in gomod.read_text(encoding="utf-8").splitlines():
            m = _GO_MODULE.match(line)
            if m:
                return m.group(1)
    except OSError:
        return None
    return None


def _go_edges(repo_root: Path, ids: set[str]) -> list[InternalEdge]:
    mod_path = _go_module_path(repo_root)
    if not mod_path:
        return []
    pkg_dirs = {Path(m).parent.as_posix() for m in ids}
    out: list[InternalEdge] = []
    for f in walk_files(repo_root, suffixes=(".go",)):
        rel = f.relative_to(repo_root).as_posix()
        from_id = _strip_suffix(rel)
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        in_block = False
        for i, line in enumerate(lines, 1):
            spec = None
            if line.strip().startswith("import ("):
                in_block = True
                continue
            if in_block:
                if ")" in line:
                    in_block = False
                m = _GO_IMPORT_BLOCK_LINE.match(line)
                if m:
                    spec = m.group(1)
            else:
                m = _GO_IMPORT_SINGLE.match(line)
                if m:
                    spec = m.group(1)
            if spec and spec.startswith(mod_path + "/"):
                sub = spec[len(mod_path) + 1:]
                if sub and sub in pkg_dirs:
                    target = next((m2 for m2 in sorted(ids)
                                   if Path(m2).parent.as_posix() == sub), None)
                    if target and target != from_id:
                        out.append(InternalEdge(from_id, target, rel, i, line.strip()))
    return out


# --- Dispatch --------------------------------------------------------------

def extract_internal_edges(repo_root: Path, modules: list[ModuleNode]) -> list[InternalEdge]:
    by_lang: dict[str, set[str]] = {}
    for m in modules:
        by_lang.setdefault(m.language, set()).add(m.id)
    edges: list[InternalEdge] = []
    edges += _python_edges(repo_root, by_lang.get("python", set()))
    edges += _js_edges(repo_root, by_lang.get("javascript", set()))
    edges += _rust_edges(repo_root, by_lang.get("rust", set()))
    edges += _go_edges(repo_root, by_lang.get("go", set()))
    return sorted(edges, key=lambda e: (e.from_id, e.to_id, e.evidence_file, e.evidence_line or 0))
