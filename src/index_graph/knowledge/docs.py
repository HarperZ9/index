"""Discover + parse workspace markdown into Doc nodes for the atlas."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..graph.walk import walk_files

_MD_SUFFIXES = (".md", ".markdown")
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# [[target]] or [[target|alias]]: capture target only
_WIKILINK = re.compile(r"\[\[\s*([^\]|]+?)\s*(?:\|[^\]]*)?\]\]")


def _norm(s: str) -> str:
    return s.strip().lower().replace("_", "-").replace(" ", "-")


@dataclass(frozen=True)
class Doc:
    rel_path: str                  # workspace-relative, forward-slashed (stable id)
    title: str                     # first H1, else filename stem
    body: str                      # raw markdown
    link_targets: tuple[str, ...]  # normalized [[wiki-link]] targets, sorted-unique
    dir_rel: str                   # workspace-relative dir ("" at root)


def _parse_doc(rel_path: str, text: str) -> Doc:
    m = _H1.search(text)
    title = m.group(1).strip() if m else Path(rel_path).stem
    targets = tuple(sorted({_norm(t) for t in _WIKILINK.findall(text)}))
    parent = Path(rel_path).parent.as_posix()
    return Doc(rel_path, title, text, targets, "" if parent == "." else parent)


def discover_docs(root: Path) -> list[Doc]:
    """All markdown under `root` (pruned dirs excluded), as Docs sorted by rel_path."""
    out: list[Doc] = []
    for p in walk_files(root, suffixes=_MD_SUFFIXES):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append(_parse_doc(p.relative_to(root).as_posix(), text))
    out.sort(key=lambda d: d.rel_path)
    return out
