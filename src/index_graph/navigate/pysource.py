"""Leaf spans for one source file: symbols for Python, line blocks for the rest.

Each span is (kind, qualname, start, end, description, text) with 1-indexed,
inclusive lines. Every line of a Python file belongs to exactly one leaf: a
top-level function, a method, a class header, or the module block (imports,
constants and anything else outside a def), so delivering leaves never hides
code from a reader who asks for the whole file.
"""
from __future__ import annotations

import ast
from collections import Counter

BLOCK_LINES = 80
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _doc(node: ast.AST) -> str:
    try:
        doc = ast.get_docstring(node) or ""
    except TypeError:
        return ""
    return doc.split("\n\n")[0][:400]


def _names(node: ast.AST, limit: int = 40) -> list[str]:
    """The most frequent identifiers and attribute names used inside ``node``."""
    seen: Counter = Counter()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            seen[sub.id] += 1
        elif isinstance(sub, ast.Attribute):
            seen[sub.attr] += 1
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            seen.update(w for w in sub.value.split()[:6] if w.isidentifier())
    return [name for name, _ in seen.most_common(limit)]


def _signature(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        return ", ".join(ast.unparse(b) for b in node.bases)
    args = node.args  # type: ignore[attr-defined]
    return ", ".join(a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs])


def _describe(node: ast.AST, kind: str, qual: str) -> str:
    return " ".join([kind, qual, _signature(node), _doc(node), " ".join(_names(node))])


def _start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(d.lineno for d in decorators)])


def _class_spans(node: ast.ClassDef, end: int) -> list[tuple]:
    methods = [c for c in node.body if isinstance(c, _DEFS)]
    if not methods:
        return [("class", node.name, _start(node), end, _describe(node, "class", node.name))]
    header_end = _start(methods[0]) - 1
    spans = [("class", node.name, _start(node), header_end,
              " ".join(["class", node.name, _signature(node), _doc(node),
                        " ".join(m.name for m in methods)]))]
    for i, m in enumerate(methods):
        m_end = (_start(methods[i + 1]) - 1) if i + 1 < len(methods) else end
        qual = f"{node.name}.{m.name}"
        spans.append(("method", qual, _start(m), m_end, _describe(m, "method", qual)))
    return spans


def python_spans(text: str) -> tuple[list[tuple], str] | None:
    """Leaf spans and the module docstring for Python ``text``; None if it does not parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    total = max(text.count("\n") + (0 if text.endswith("\n") else 1), 1)
    tops = [n for n in tree.body if isinstance(n, _DEFS)]
    spans: list[tuple] = []
    covered: set[int] = set()
    for i, node in enumerate(tops):
        end = node.end_lineno or node.lineno
        if isinstance(node, ast.ClassDef):
            spans.extend(_class_spans(node, end))
        else:
            spans.append(("function", node.name, _start(node), end,
                          _describe(node, "function", node.name)))
        covered.update(range(_start(node), end + 1))
    rest = [n for n in range(1, total + 1) if n not in covered]
    if rest:
        module_names = " ".join(_names(ast.Module(
            body=[n for n in tree.body if not isinstance(n, _DEFS)], type_ignores=[])))
        spans.append(("module", "<module>", rest[0], rest[-1],
                      "module " + _doc(tree) + " " + module_names))
    spans.sort(key=lambda s: s[2])
    lines = text.splitlines()
    own = set(rest)
    out = []
    for kind, qual, start, end, desc in spans:
        picked = [n for n in range(start, end + 1) if kind != "module" or n in own]
        out.append((kind, qual, start, end, desc,
                    "\n".join(lines[n - 1] for n in picked if 0 < n <= len(lines))))
    return out, _doc(tree)


def block_spans(text: str) -> list[tuple]:
    """Fixed line blocks for non-Python text; the description is the block itself."""
    lines = text.splitlines()
    spans = []
    for start in range(0, max(len(lines), 1), BLOCK_LINES):
        chunk = lines[start:start + BLOCK_LINES]
        end = start + max(len(chunk), 1)
        body = "\n".join(chunk)
        spans.append(("block", f"lines {start + 1}-{end}", start + 1, end, body, body))
    return spans
