"""Rust ecosystem resolver: Cargo.toml manifests + a use/extern-crate scan."""
from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_DEP_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")
_USE = re.compile(r"^\s*use\s+([A-Za-z_][A-Za-z0-9_]*)")
_EXTERN = re.compile(r"^\s*extern\s+crate\s+([A-Za-z_][A-Za-z0-9_]*)")
_INTRA = {"crate", "self", "super"}   # path roots that name the current crate, not a dep


class RustResolver:
    name = "rust"
    # files whose content feeds the graph (read by the freshness fingerprint)
    fingerprint_names = ("Cargo.toml",)
    fingerprint_suffixes = (".rs",)

    def matches(self, repo_root: Path) -> bool:
        return (repo_root / "Cargo.toml").is_file()

    def _manifests(self, repo_root: Path) -> Iterator[Path]:
        return walk_files(repo_root, names=("Cargo.toml",))

    def exposed_names(self, repo_root: Path) -> set[str]:
        names: set[str] = set()
        for ct in self._manifests(repo_root):
            try:
                data = tomllib.loads(ct.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, OSError):
                continue
            pkg = data.get("package", {})
            if isinstance(pkg, dict) and pkg.get("name"):
                names.add(str(pkg["name"]))
        return names

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []
        for ct in self._manifests(repo_root):
            try:
                data = tomllib.loads(ct.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, OSError):
                continue
            rel = ct.relative_to(repo_root).as_posix()
            for table in _DEP_TABLES:
                section = data.get(table, {})
                if isinstance(section, dict):
                    for name in section:
                        edges.append(RawEdge(str(name), "manifest", rel, None, f"{table}.{name}"))
        for src in walk_files(repo_root, suffixes=(".rs",)):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                m = _USE.match(line) or _EXTERN.match(line)
                if m and m.group(1) not in _INTRA:
                    edges.append(RawEdge(m.group(1), "import", rel, i, line.strip()))
        return edges
