"""The outline: a repository as a tree of directories, files and leaves.

The outline is the external state the navigator walks. No single question sees
all of it: each level offers only the children of one node, as a map. Leaves
carry their source text; inner nodes carry a short description built from the
names and the most distinctive terms beneath them.
"""
from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..graph.walk import EXCLUDE_DIRS
from .pysource import block_spans, python_spans
from .text import tokens

CODE_SUFFIXES = frozenset({
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".sh", ".ps1",
})
DOC_SUFFIXES = frozenset({
    ".md", ".rst", ".txt", ".toml", ".cfg", ".ini", ".json", ".yml", ".yaml", ".html", ".css",
})
MAX_FILE_BYTES = 256 * 1024
SUMMARY_TERMS = 400


@dataclass
class Node:
    id: str
    kind: str                 # "dir" | "file" | a leaf kind from pysource
    name: str
    file: str | None = None
    start: int = 0
    end: int = 0
    description: str = ""
    text: str = ""
    children: list["Node"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children


@dataclass
class Outline:
    root: Node
    leaves: list[Node]
    idf: dict[str, float]
    files: dict[str, str]     # repo-relative path -> full text, for the whole-file arms


def _candidate_files(root: Path, suffixes: frozenset[str]) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in EXCLUDE_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix.lower() in suffixes:
                found.append(path)
    return found


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def _file_node(rel: str, text: str) -> Node:
    parsed = python_spans(text) if rel.endswith((".py", ".pyi")) else None
    spans, doc = parsed if parsed else (block_spans(text), "")
    node = Node(id=rel, kind="file", name=rel.rsplit("/", 1)[-1], file=rel,
                start=1, end=max(text.count("\n"), 1), description=f"{rel} {doc}")
    for kind, qual, start, end, desc, body in spans:
        node.children.append(Node(id=f"{rel}::{qual}", kind=kind, name=qual, file=rel,
                                  start=start, end=end, description=f"{rel} {desc}",
                                  text=body))
    return node


def _attach(root: Node, rel: str, node: Node) -> None:
    parts = rel.split("/")[:-1]
    cursor, prefix = root, ""
    for part in parts:
        prefix = f"{prefix}{part}/"
        nxt = next((c for c in cursor.children if c.id == prefix), None)
        if nxt is None:
            nxt = Node(id=prefix, kind="dir", name=part + "/")
            cursor.children.append(nxt)
        cursor = nxt
    cursor.children.append(node)


def _summarize(node: Node, idf: dict[str, float], limit: int = SUMMARY_TERMS) -> Counter:
    """Fill inner-node descriptions bottom-up; return the subtree's term counts."""
    if node.is_leaf:
        return Counter(tokens(node.description))
    counts: Counter = Counter()
    for child in node.children:
        counts.update(_summarize(child, idf, limit))
    top = sorted(counts, key=lambda t: (-counts[t] * idf.get(t, 0.0), t))[:limit]
    names = " ".join(c.name for c in node.children)
    node.description = " ".join(filter(None, [node.description or node.id, names, " ".join(top)]))
    return counts


def build_outline(root: Path | str, *, include_docs: bool = False,
                  summary_terms: int = SUMMARY_TERMS) -> Outline:
    """Walk ``root`` and build its outline. Deterministic for a fixed tree.

    Code files only by default; ``include_docs`` adds prose and config files.
    """
    suffixes = CODE_SUFFIXES | DOC_SUFFIXES if include_docs else CODE_SUFFIXES
    root = Path(root)
    top = Node(id="", kind="dir", name=root.name + "/")
    files: dict[str, str] = {}
    for path in _candidate_files(root, suffixes):
        text = _read(path)
        if text is None:
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = text
        _attach(top, rel, _file_node(rel, text))
    leaves = [n for n in _iter(top) if n.is_leaf and n.kind not in ("dir", "file")]
    df: Counter = Counter()
    for leaf in leaves:
        df.update(set(tokens(leaf.description)))
    total = max(len(leaves), 1)
    idf = {t: math.log(1 + (total - f + 0.5) / (f + 0.5)) for t, f in df.items()}
    _summarize(top, idf, summary_terms)
    return Outline(root=top, leaves=leaves, idf=idf, files=files)


def _iter(node: Node):
    yield node
    for child in node.children:
        yield from _iter(child)
