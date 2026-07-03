"""Class inheritance and method-override edges, resolved AST-exact in-repo.

Powers find-implementations at symbol granularity. Two edge kinds, both carrying
file:line evidence and an honest resolution label:

  - a ``subclass`` edge: class C in this repo lists base B, where B binds (via a
    ``from <internal> import B`` or a same-module ``class B``) to a real class
    definition in this repo. A base that names an external class, or a name the
    static scan cannot bind, is never guessed into an edge.
  - an ``override`` edge: subclass C defines a method whose name also exists on
    a resolved ancestor class. The edge points from the override site to the
    ancestor's method, so find-implementations of ``Base::method`` returns every
    in-repo override with its exact definition line.

Only Python is AST-exact here; other languages carry no inheritance extraction,
matching the definitions/calls layers.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from ..graph.walk import walk_files
from ..internals.modules import _strip_suffix
from .model import SymbolDefinition


@dataclass(frozen=True)
class InheritanceEdge:
    """A resolved class -> base edge, or a subclass-method -> base-method override."""
    kind: str            # "subclass" | "override"
    child: str           # subclass id (subclass edge) or override method id (override edge)
    parent: str          # resolved base-class id, or ancestor method id
    name: str            # bare base-class name / method name as written
    file: str            # repo-relative path of the child site
    line: int            # 1-indexed line of the child (subclass def / override method def)
    resolution: str      # "exact" (same module) | "cross_module" (import-bound)


def _base_name(base: ast.expr) -> str | None:
    """The bare name of a base-class expression, or None for a non-name base.

    ``class C(Base)`` -> "Base"; ``class C(pkg.Base)`` -> "Base" (attribute tail);
    a subscript/call base (e.g. ``Generic[T]``) is not a bindable class name.
    """
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _class_bases(tree: ast.AST) -> dict[int, list[str]]:
    """Map each class-def line to the list of bare base names it declares."""
    bases: dict[int, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names = [n for b in node.bases if (n := _base_name(b)) is not None]
            if names:
                bases[node.lineno] = names
    return bases


def _resolve_base(
    base_name: str,
    module_id: str,
    class_by_name_in_module: dict[str, dict[str, str]],
    imports: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    """Resolve a bare base name to (class_id, resolution), or None if unbindable.

    Same-module class wins first (exact); otherwise an import binding that names
    a real class in the target module resolves cross_module. A base that binds to
    no in-repo class definition returns None and is never guessed into an edge.
    """
    same = class_by_name_in_module.get(module_id, {}).get(base_name)
    if same is not None:
        return same, "exact"
    binding = imports.get(base_name)
    if binding is not None:
        target_mod, imported = binding
        cand = class_by_name_in_module.get(target_mod, {}).get(imported)
        if cand is not None:
            return cand, "cross_module"
    return None


def _method_index(
    definitions: list[SymbolDefinition],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """(class name -> id per module, class id -> {method name -> method id})."""
    class_by_name: dict[str, dict[str, str]] = {}
    methods_of: dict[str, dict[str, str]] = {}
    for d in definitions:
        if d.kind == "class":
            class_by_name.setdefault(d.module_id, {})[d.name] = d.id
    class_ids = {i for m in class_by_name.values() for i in m.values()}
    for d in definitions:
        if d.parent in class_ids and d.kind in ("method", "async_method"):
            methods_of.setdefault(d.parent, {})[d.name] = d.id
    return class_by_name, methods_of


def extract_inheritance_edges(
    repo_root: Path,
    definitions: list[SymbolDefinition],
    ids: set[str],
    import_tables: dict[str, dict[str, tuple[str, str]]],
) -> list[InheritanceEdge]:
    """Return resolved subclass + override edges, sorted deterministically.

    Overrides are computed against the direct resolved parent only; a diamond or
    multi-level chain still yields one override edge per resolved parent that
    declares the same method name, which is the honest, re-checkable claim.
    """
    class_by_name, methods_of = _method_index(definitions)
    class_line_to_id = {(d.file, d.line): d.id
                        for d in definitions if d.kind == "class"}
    site_of = {d.id: (d.file, d.line) for d in definitions}
    edges: list[InheritanceEdge] = []
    for py in walk_files(repo_root, suffixes=(".py",)):
        rel = py.relative_to(repo_root).as_posix()
        module_id = _strip_suffix(rel)
        if module_id not in ids:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, ValueError):
            continue
        imports = import_tables.get(module_id, {})
        for line, base_names in _class_bases(tree).items():
            child_id = class_line_to_id.get((rel, line))
            if child_id is None:
                continue
            for base_name in base_names:
                resolved = _resolve_base(base_name, module_id, class_by_name, imports)
                if resolved is None:
                    continue  # external or unbindable base: never guessed
                parent_id, resolution = resolved
                edges.append(InheritanceEdge(
                    kind="subclass", child=child_id, parent=parent_id,
                    name=base_name, file=rel, line=line, resolution=resolution))
                edges.extend(_override_edges(
                    child_id, parent_id, resolution, methods_of, site_of))
    edges.sort(key=lambda e: (e.kind, e.child, e.parent, e.name, e.file, e.line))
    return _dedupe(edges)


def _override_edges(
    child_id: str, parent_id: str, resolution: str,
    methods_of: dict[str, dict[str, str]],
    site_of: dict[str, tuple[str, int]],
) -> list[InheritanceEdge]:
    """Override edges for every child method whose name the parent also defines.

    The edge's file:line is the override method's own definition site, taken
    from the definition table so every hop stays evidence-backed.
    """
    child_methods = methods_of.get(child_id, {})
    parent_methods = methods_of.get(parent_id, {})
    out: list[InheritanceEdge] = []
    for mname, mid in sorted(child_methods.items()):
        parent_mid = parent_methods.get(mname)
        if parent_mid is None:
            continue
        file, line = site_of.get(mid, ("", 0))
        out.append(InheritanceEdge(
            kind="override", child=mid, parent=parent_mid, name=mname,
            file=file, line=line, resolution=resolution))
    return out


def _dedupe(edges: list[InheritanceEdge]) -> list[InheritanceEdge]:
    seen: set[tuple] = set()
    out: list[InheritanceEdge] = []
    for e in edges:
        key = (e.kind, e.child, e.parent, e.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out
