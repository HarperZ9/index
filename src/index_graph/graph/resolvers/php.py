"""PHP ecosystem resolver: composer.json require/require-dev + use-statement scan."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

# `use Ns\Thing;`, and also `use function Ns\fn;` / `use const Ns\C;`: a symbol
# import still depends on namespace Ns, so the optional function/const modifier is
# consumed and the leading namespace segment is captured as the target. The trailing
# \s+ in the modifier keeps a namespace that merely starts with "function" (say
# `use functional\X;`) from being mistaken for the keyword.
_USE_STMT = re.compile(
    r"^\s*use\s+(?:function\s+|const\s+)?\\?([A-Za-z_][A-Za-z0-9_]*)(?:\\[^;]*)?\s*;"
)


class PhpResolver:
    name = "php"
    # files whose content feeds the graph (read by the freshness fingerprint)
    fingerprint_names = ("composer.json",)
    fingerprint_suffixes = (".php",)

    def matches(self, repo_root: Path) -> bool:
        return (repo_root / "composer.json").is_file()

    def exposed_names(self, repo_root: Path) -> set[str]:
        cj = repo_root / "composer.json"
        if not cj.is_file():
            return set()
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return set()
        name = data.get("name")
        return {str(name)} if name else set()

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []
        cj = repo_root / "composer.json"
        if cj.is_file():
            try:
                data = json.loads(cj.read_text(encoding="utf-8"))
                for field in ("require", "require-dev"):
                    for pkg, spec in (data.get(field, {}) or {}).items():
                        edges.append(RawEdge(str(pkg), "manifest", "composer.json", None, f"{pkg}: {spec}"))
            except (json.JSONDecodeError, OSError):
                pass
        for src in walk_files(repo_root, suffixes=(".php",)):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                m = _USE_STMT.match(line)
                if m:
                    edges.append(RawEdge(m.group(1), "import", rel, i, line.strip()))
        return edges
