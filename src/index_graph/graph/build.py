"""Assemble repo trees + resolvers into a DependencyGraph."""
from __future__ import annotations

import configparser
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .edges import Edge, build_index, resolve_edges
from .walk import walk_budget, walk_files
from .resolvers import ALL_RESOLVERS
from .resolvers.base import RawEdge
from .roles import derive_roles

_PARA = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class RepoNode:
    name: str
    path: str
    ecosystems: tuple[str, ...]
    exposed_names: frozenset[str]
    description: str
    markers: frozenset[str]


@dataclass(frozen=True)
class DependencyGraph:
    repos: tuple[RepoNode, ...]
    edges: tuple[Edge, ...]
    roles: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]


def _description(repo_root: Path, document_reader=None) -> str:
    for readme in ("README.md", "README.rst", "README.txt", "readme.md"):
        p = repo_root / readme
        if p.is_file():
            try:
                if document_reader is not None and p.suffix.lower() == ".md":
                    text = document_reader(p)
                    if text is None:
                        continue
                    text = text.strip()
                else:
                    text = p.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            for block in _PARA.split(text):
                b = block.strip()
                if b and not b.startswith("#") and not b.startswith("!["):
                    return " ".join(b.split())[:300]
    pp = repo_root / "pyproject.toml"
    if pp.is_file():
        try:
            d = tomllib.loads(pp.read_text(encoding="utf-8", errors="replace")).get("project", {})
            if d.get("description"):
                return str(d["description"])
        except (tomllib.TOMLDecodeError, OSError):
            pass
    pj = repo_root / "package.json"
    if pj.is_file():
        try:
            d = json.loads(pj.read_text(encoding="utf-8", errors="replace"))
            if d.get("description"):
                return str(d["description"])
        except (json.JSONDecodeError, OSError):
            pass
    return "(no description)"


def detect_markers(repo_root: Path, exposed: set[str]) -> set[str]:
    mk: set[str] = set()
    if exposed:
        mk.add("published")
    pp = repo_root / "pyproject.toml"
    if pp.is_file():
        try:
            data = tomllib.loads(pp.read_text(encoding="utf-8", errors="replace"))
            if data.get("project", {}).get("scripts") or \
               data.get("project", {}).get("entry-points"):
                mk.add("entry")
        except (tomllib.TOMLDecodeError, OSError):
            pass
    cfg = repo_root / "setup.cfg"
    if cfg.is_file():
        try:
            cp = configparser.ConfigParser()
            cp.read(cfg, encoding="utf-8")
            if cp.has_option("options.entry_points", "console_scripts"):
                mk.add("entry")
        except (configparser.Error, OSError):
            pass
    pj = repo_root / "package.json"
    if pj.is_file():
        try:
            if json.loads(pj.read_text(encoding="utf-8", errors="replace")).get("bin"):
                mk.add("entry")
        except (json.JSONDecodeError, OSError):
            pass
    if any(walk_files(repo_root, names=("__main__.py",))):
        mk.add("entry")
    return mk


def build_graph(
    repo_paths: dict[str, Path],
    resolvers=ALL_RESOLVERS,
    *,
    checkpoint=None,
    document_reader=None,
) -> DependencyGraph:
    nodes: list[RepoNode] = []
    exposed: dict[str, set[str]] = {}
    repo_raw: dict[str, list[RawEdge]] = {}
    markers: dict[str, set[str]] = {}
    exhausted_boundary: str | None = None

    def checked(boundary: str) -> bool:
        nonlocal exhausted_boundary
        if exhausted_boundary is not None:
            return False
        allowed = checkpoint is None or checkpoint(boundary)
        if not allowed:
            exhausted_boundary = boundary
        return allowed

    with walk_budget(checked if checkpoint is not None else None):
        for name, root in sorted(repo_paths.items()):
            if not checked("graph.repo"):
                break
            ecos: list[str] = []
            names: set[str] = set()
            raws: list[RawEdge] = []
            for r in resolvers:
                if not checked("graph.resolver"):
                    break
                if r.matches(root):
                    if exhausted_boundary is not None:
                        break
                    ecos.append(r.name)
                    names |= r.exposed_names(root)
                    if exhausted_boundary is not None:
                        break
                    raws += r.raw_edges(root)
            if exhausted_boundary is not None:
                break
            exposed[name] = names
            repo_raw[name] = raws
            mk = detect_markers(root, names)
            if exhausted_boundary is not None:
                break
            markers[name] = mk
            nodes.append(RepoNode(name, str(root), tuple(ecos), frozenset(names),
                                  _description(root, document_reader), frozenset(mk)))

    index = build_index(exposed)
    edges, warnings = resolve_edges(repo_raw, index)
    if exhausted_boundary is not None:
        warnings.append(f"budget-exhausted:{exhausted_boundary}")
    roles = derive_roles(set(repo_paths), edges, markers)
    return DependencyGraph(tuple(nodes), tuple(edges), roles, tuple(warnings))
