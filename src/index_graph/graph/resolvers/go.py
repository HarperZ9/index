"""Go ecosystem resolver: go.mod requires + an import-path scan."""
from __future__ import annotations

import re
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_MODULE = re.compile(r"^\s*module\s+(\S+)")
_REQUIRE_SINGLE = re.compile(r"^\s*require\s+(\S+)\s+\S+")
_IMPORT_SINGLE = re.compile(r'^\s*import\s+(?:[A-Za-z0-9_.]+\s+)?"([^"]+)"')
_GROUPED_IMPORT = re.compile(r'^\s*(?:[A-Za-z0-9_.]+\s+)?"([^"]+)"')


class GoResolver:
    name = "go"
    # files whose content feeds the graph (read by the freshness fingerprint)
    fingerprint_names = ("go.mod",)
    fingerprint_suffixes = (".go",)

    def matches(self, repo_root: Path) -> bool:
        return (repo_root / "go.mod").is_file()

    def exposed_names(self, repo_root: Path) -> set[str]:
        gm = repo_root / "go.mod"
        try:
            for line in gm.read_text(encoding="utf-8").splitlines():
                m = _MODULE.match(line)
                if m:
                    return {m.group(1)}
        except OSError:
            pass
        return set()

    def _require_paths(self, text: str) -> list[str]:
        out: list[str] = []
        in_block = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("require (") or s == "require (":
                in_block = True
                continue
            if in_block:
                if s == ")":
                    in_block = False
                elif s and not s.startswith("//"):
                    out.append(s.split()[0])
                continue
            m = _REQUIRE_SINGLE.match(line)
            if m:
                out.append(m.group(1))
        return out

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []
        gm = repo_root / "go.mod"
        if gm.is_file():
            try:
                for path in self._require_paths(gm.read_text(encoding="utf-8")):
                    edges.append(RawEdge(path, "manifest", "go.mod", None, f"require {path}"))
            except OSError:
                pass
        for src in walk_files(repo_root, suffixes=(".go",)):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            in_block = False
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if s.startswith("import ("):
                    in_block = True
                    continue
                if in_block:
                    if s == ")":
                        in_block = False
                        continue
                    m = _GROUPED_IMPORT.match(s)
                    if m:
                        edges.append(RawEdge(m.group(1), "import", rel, i, s))
                    continue
                m = _IMPORT_SINGLE.match(line)
                if m:
                    edges.append(RawEdge(m.group(1), "import", rel, i, s))
        return edges
