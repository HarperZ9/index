"""C#/.NET ecosystem resolver: .csproj manifest + using-statement scan."""
from __future__ import annotations

import re
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_ASSEMBLY_NAME = re.compile(r"<AssemblyName>\s*([^<]+)\s*</AssemblyName>")
_ROOT_NAMESPACE = re.compile(r"<RootNamespace>\s*([^<]+)\s*</RootNamespace>")
_PKG_REF = re.compile(r'<PackageReference\s[^>]*Include="([^"]+)"', re.IGNORECASE)
_PROJ_REF = re.compile(r'<ProjectReference\s[^>]*Include="([^"]+)"', re.IGNORECASE)
_USING = re.compile(r"^\s*using\s+([\w.]+)\s*;")


class CSharpResolver:
    name = "csharp"
    # files whose content feeds the graph (read by the freshness fingerprint)
    fingerprint_suffixes = (".csproj", ".cs")

    def matches(self, repo_root: Path) -> bool:
        # walk_files is fail-closed (never raises on a permission-denied subdir)
        # and pruned; rglob would propagate an OSError out and crash the graph build.
        return any(walk_files(repo_root, suffixes=(".csproj",)))

    def exposed_names(self, repo_root: Path) -> set[str]:
        names: set[str] = set()
        for csproj in walk_files(repo_root, suffixes=(".csproj",)):
            names.add(csproj.stem)
            try:
                text = csproj.read_text(encoding="utf-8")
            except OSError:
                continue
            for pattern in (_ASSEMBLY_NAME, _ROOT_NAMESPACE):
                m = pattern.search(text)
                if m:
                    names.add(m.group(1).strip())
        return names

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []

        # manifest edges: parse each .csproj for PackageReference and ProjectReference
        for csproj in walk_files(repo_root, suffixes=(".csproj",)):
            try:
                lines = csproj.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = csproj.relative_to(repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                m = _PKG_REF.search(line)
                if m:
                    pkg = m.group(1).strip()
                    edges.append(RawEdge(pkg, "manifest", rel, i, line.strip()))
                    continue
                m = _PROJ_REF.search(line)
                if m:
                    # target is the stem of the referenced .csproj path
                    ref_stem = Path(m.group(1).replace("\\", "/")).stem
                    edges.append(RawEdge(ref_stem, "manifest", rel, i, line.strip()))

        # import edges: scan .cs files for using statements
        for src in walk_files(repo_root, suffixes=(".cs",)):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                m = _USING.match(line)
                if m:
                    # target is the top-level namespace segment
                    top = m.group(1).split(".")[0]
                    edges.append(RawEdge(top, "import", rel, i, line.strip()))

        return edges
