"""Java ecosystem resolver: Maven pom.xml + best-effort Gradle. Manifest-only."""
from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from ..walk import walk_files
from .base import RawEdge

_GRADLE_FILES = ("build.gradle", "build.gradle.kts")
_GRADLE_DEP = re.compile(
    r"""(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*[(\s]\s*"""
    r"""['"]([^'":]+:[^'":]+):[^'"]+['"]""")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]   # strip the {namespace}


def _pom_coords(pom: Path) -> tuple[str, str] | None:
    """The pom's own (groupId, artifactId), falling back to <parent><groupId>."""
    try:
        root = ET.parse(pom).getroot()
    except (ET.ParseError, OSError):
        return None
    group = artifact = parent_group = None
    for child in root:
        t = _local(child.tag)
        if t == "groupId":
            group = (child.text or "").strip()
        elif t == "artifactId":
            artifact = (child.text or "").strip()
        elif t == "parent":
            for pc in child:
                if _local(pc.tag) == "groupId":
                    parent_group = (pc.text or "").strip()
    group = group or parent_group
    return (group, artifact) if (group and artifact) else None


class JavaResolver:
    name = "java"
    # files whose content feeds the graph (read by the freshness fingerprint); manifest-only
    fingerprint_names = ("pom.xml", "build.gradle", "build.gradle.kts")

    def matches(self, repo_root: Path) -> bool:
        return ((repo_root / "pom.xml").is_file()
                or any((repo_root / g).is_file() for g in _GRADLE_FILES))

    def exposed_names(self, repo_root: Path) -> set[str]:
        names: set[str] = set()
        for pom in walk_files(repo_root, names=("pom.xml",)):
            coords = _pom_coords(pom)
            if coords:
                names.add(f"{coords[0]}:{coords[1]}")
        return names

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []
        for pom in walk_files(repo_root, names=("pom.xml",)):
            try:
                root = ET.parse(pom).getroot()
            except (ET.ParseError, OSError):
                continue
            rel = pom.relative_to(repo_root).as_posix()
            for dep in root.iter():
                if _local(dep.tag) != "dependency":
                    continue
                group = artifact = None
                for c in dep:
                    t = _local(c.tag)
                    if t == "groupId":
                        group = (c.text or "").strip()
                    elif t == "artifactId":
                        artifact = (c.text or "").strip()
                if group and artifact:
                    coord = f"{group}:{artifact}"
                    edges.append(RawEdge(coord, "manifest", rel, None, coord))
        for gf in _GRADLE_FILES:
            gp = repo_root / gf
            if not gp.is_file():
                continue
            try:
                lines = gp.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                m = _GRADLE_DEP.search(line)
                if m:
                    edges.append(RawEdge(m.group(1), "manifest", gf, i, line.strip()))
        return edges
