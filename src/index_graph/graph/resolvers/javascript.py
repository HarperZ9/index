"""JavaScript/TypeScript resolver: package.json + conservative import scan."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
_IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*|require\(\s*|import\(\s*)['"]([^'"]+)['"]""")


def _bare_package(spec: str) -> str | None:
    """Return the package name for a bare specifier, else None for relative/absolute paths."""
    if spec.startswith(".") or spec.startswith("/"):
        return None
    parts = spec.split("/")
    if spec.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


class JavaScriptResolver:
    name = "javascript"
    # files whose content feeds the graph (read by the freshness fingerprint)
    fingerprint_names = ("package.json",)
    fingerprint_suffixes = _EXTS

    def matches(self, repo_root: Path) -> bool:
        return (repo_root / "package.json").is_file()

    def exposed_names(self, repo_root: Path) -> set[str]:
        pj = repo_root / "package.json"
        if not pj.is_file():
            return set()
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return set()
        name = data.get("name")
        return {str(name)} if name else set()

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []
        pj = repo_root / "package.json"
        if pj.is_file():
            try:
                data = json.loads(pj.read_text(encoding="utf-8"))
                for field in ("dependencies", "devDependencies", "peerDependencies"):
                    for name, spec in (data.get(field, {}) or {}).items():
                        edges.append(RawEdge(str(name), "manifest", "package.json", None, f"{name}: {spec}"))
            except (json.JSONDecodeError, OSError):
                pass
        for src in walk_files(repo_root, suffixes=_EXTS):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                for m in _IMPORT.finditer(line):
                    pkg = _bare_package(m.group(1))
                    if pkg:
                        edges.append(RawEdge(pkg, "import", rel, i, line.strip()))
        return edges
