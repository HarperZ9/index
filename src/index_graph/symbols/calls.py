"""Extract call sites and resolve them: exact within-module, best-effort cross-module.

Resolution is layered and honest:
  - ``foo()`` where ``foo`` is defined at module level in this file -> exact/high.
  - ``self.m()`` inside a method of class C where C defines ``m`` -> exact/high.
  - ``foo()`` where ``foo`` is a ``from <internal> import foo`` binding that
    names a real definition in the target module -> cross_module/moderate.
  - anything else (undefined name, attribute on a non-self object, a name that
    imports but names no definition) -> cross_module_unresolved/low, never guessed.
  - ``getattr(...)`` / a call whose func is neither a Name nor an Attribute
    (a variable holding a function) -> flagged as a dynamic-dispatch coverage gap.
"""
from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

from ..graph.walk import walk_files
from ..internals.modules import _strip_suffix
from .model import SymbolCall, SymbolDefinition

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_DEF = (*_FUNC, ast.ClassDef)


def _line_text(lines: list[str], lineno: int) -> str:
    return lines[lineno - 1].strip() if 1 <= lineno <= len(lines) else ""


def _is_getattr(func: ast.AST) -> bool:
    return isinstance(func, ast.Name) and func.id == "getattr"


class _Walker:
    """Walk one module's AST, emitting a SymbolCall per resolvable/unresolvable
    call site and recording dynamic-dispatch sites as coverage gaps."""

    def __init__(self, module_id: str, rel: str, lines: list[str],
                 local_defs: dict[str, str], class_methods: dict[str, dict[str, str]],
                 imports: dict[str, tuple[str, str]],
                 cross_target: Callable[[tuple[str, str]], str | None]):
        self.module_id = module_id
        self.rel = rel
        self.lines = lines
        self.local_defs = local_defs          # bare name -> module-level symbol id
        self.class_methods = class_methods     # class id -> {method name -> method id}
        self.imports = imports                 # bare name -> (target_module_id, name)
        self.cross_target = cross_target       # (module_id, name) -> resolved symbol id | None
        self.calls: list[SymbolCall] = []
        self.dynamic: list[tuple[str, int]] = []

    def visit_body(self, body, enclosing: str | None, parent_id: str | None,
                   class_id: str | None) -> None:
        """`enclosing` is the caller symbol calls are attributed to; `parent_id`
        is the lexical id used to build child symbol ids (matches definitions.py);
        `class_id` is the nearest enclosing class, for `self.m()` resolution."""
        for node in body:
            self._visit(node, enclosing, parent_id, class_id)

    def _visit(self, node: ast.AST, enclosing: str | None, parent_id: str | None,
               class_id: str | None) -> None:
        if isinstance(node, ast.ClassDef):
            base = parent_id or self.module_id
            cid = f"{base}::{node.name}"
            # class-level statements have no caller symbol; class_id becomes cid
            self.visit_body(node.body, enclosing=None, parent_id=cid, class_id=cid)
            return
        if isinstance(node, _FUNC):
            base = parent_id or self.module_id
            sym_id = f"{base}::{node.name}"
            # class_id persists into the function body so `self.m()` resolves
            # against the enclosing class (also for nested closures in a method).
            self.visit_body(node.body, enclosing=sym_id, parent_id=sym_id,
                            class_id=class_id)
            return
        # a plain statement: collect its calls, but hand any nested def/class
        # back to _visit so their bodies are attributed to the right symbol.
        self._scan(node, enclosing, parent_id, class_id)

    def _scan(self, node: ast.AST, enclosing: str | None, parent_id: str | None,
              class_id: str | None) -> None:
        """Recurse a statement's expression tree, emitting calls attributed to
        `enclosing`, but re-dispatch nested defs/classes to `_visit` (they open a
        new caller scope) so their inner calls are not mis-attributed."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEF):
                self._visit(child, enclosing, parent_id, class_id)
                continue
            if isinstance(child, ast.Call):
                self._call(child, enclosing, class_id)
            self._scan(child, enclosing, parent_id, class_id)

    def _call(self, node: ast.Call, enclosing: str | None, class_id: str | None) -> None:
        if enclosing is None:
            return  # module/class-level calls have no caller symbol to attribute
        func = node.func
        if _is_getattr(func):
            self.dynamic.append((self.rel, node.lineno))
            return
        if isinstance(func, ast.Name):
            self._resolve_name(func.id, node.lineno, enclosing)
        elif isinstance(func, ast.Attribute):
            self._resolve_attr(func, node.lineno, enclosing, class_id)
        else:
            # a call on a subscript/call result: a variable function, dynamic
            self.dynamic.append((self.rel, node.lineno))

    def _resolve_name(self, name: str, lineno: int, enclosing: str) -> None:
        raw = _line_text(self.lines, lineno)
        local = self.local_defs.get(name)
        if local is not None:
            self._emit(enclosing, local, name, lineno, raw, "exact", "high")
            return
        binding = self.imports.get(name)
        if binding is not None:
            resolved = self.cross_target(binding)
            if resolved is not None:
                self._emit(enclosing, resolved, name, lineno, raw, "cross_module", "moderate")
                return
        self._emit(enclosing, None, name, lineno, raw, "cross_module_unresolved", "low")

    def _resolve_attr(self, func: ast.Attribute, lineno: int, enclosing: str,
                      class_id: str | None) -> None:
        raw = _line_text(self.lines, lineno)
        obj = func.value
        # self.method() inside a method of a known class -> exact sibling lookup
        if isinstance(obj, ast.Name) and obj.id == "self" and class_id is not None:
            methods = self.class_methods.get(class_id, {})
            target = methods.get(func.attr)
            if target is not None:
                self._emit(enclosing, target, func.attr, lineno, raw, "exact", "high")
                return
        # any other attribute call: object type is not statically known
        self._emit(enclosing, None, func.attr, lineno, raw, "cross_module_unresolved", "low")

    def _emit(self, frm: str, to: str | None, to_name: str, lineno: int,
              raw: str, resolution: str, confidence: str) -> None:
        self.calls.append(SymbolCall(
            from_symbol=frm, to_symbol=to, to_name=to_name, kind="call",
            evidence_file=self.rel, evidence_line=lineno, raw=raw,
            resolution=resolution, confidence=confidence))


def _module_maps(definitions: list[SymbolDefinition], module_id: str
                 ) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """(module-level name -> id, class id -> {method name -> id}) for one module."""
    local_defs: dict[str, str] = {}
    class_methods: dict[str, dict[str, str]] = {}
    for d in definitions:
        if d.module_id != module_id:
            continue
        if d.parent is None:
            local_defs[d.name] = d.id
        elif d.parent in {c.id for c in definitions
                          if c.module_id == module_id and c.kind == "class"}:
            class_methods.setdefault(d.parent, {})[d.name] = d.id
    return local_defs, class_methods


def extract_symbol_calls(
    repo_root: Path, definitions: list[SymbolDefinition], ids: set[str],
    import_tables: dict[str, dict[str, tuple[str, str]]],
) -> tuple[list[SymbolCall], list[tuple[str, int]]]:
    """Return (calls sorted deterministically, dynamic-dispatch sites)."""
    by_def_id = {d.id for d in definitions}

    def cross_target(binding: tuple[str, str]) -> str | None:
        target_mod, name = binding
        cand = f"{target_mod}::{name}"
        return cand if cand in by_def_id else None

    calls: list[SymbolCall] = []
    dynamic: list[tuple[str, int]] = []
    for py in walk_files(repo_root, suffixes=(".py",)):
        rel = py.relative_to(repo_root).as_posix()
        module_id = _strip_suffix(rel)
        if module_id not in ids:
            continue
        try:
            text = py.read_text(encoding="utf-8-sig")
            tree = ast.parse(text)
        except (OSError, SyntaxError, ValueError):
            continue
        local_defs, class_methods = _module_maps(definitions, module_id)
        walker = _Walker(module_id, rel, text.splitlines(), local_defs,
                         class_methods, import_tables.get(module_id, {}), cross_target)
        walker.visit_body(tree.body, enclosing=None, parent_id=None, class_id=None)
        calls += walker.calls
        dynamic += walker.dynamic
    calls.sort(key=lambda c: (c.from_symbol, c.to_symbol or "", c.to_name,
                              c.evidence_file, c.evidence_line))
    dynamic = sorted(set(dynamic))
    return calls, dynamic
