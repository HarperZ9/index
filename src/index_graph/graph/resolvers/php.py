"""PHP ecosystem resolver: composer.json require/require-dev + use-statement scan."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_USE_STMT = re.compile(r"^\s*use\s+\\?([A-Za-z_][A-Za-z0-9_]*)(?:\\[^;]*)?\s*;")


class PhpResolver:
    name = "php"

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
                if m and m.group(1) not in ("function", "const"):
                    edges.append(RawEdge(m.group(1), "import", rel, i, line.strip()))
        return edges
