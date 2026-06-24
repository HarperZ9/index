"""Python ecosystem resolver: manifests + AST import scan."""
from __future__ import annotations

import ast
import configparser
import re
import tomllib
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_MANIFESTS = ("pyproject.toml", "setup.cfg", "setup.py")


def _dep_name(spec: str) -> str | None:
    m = _PEP508_NAME.match(spec)
    return m.group(1) if m else None


class PythonResolver:
    name = "python"

    def matches(self, repo_root: Path) -> bool:
        if any((repo_root / m).is_file() for m in _MANIFESTS):
            return True
        return any(repo_root.glob("requirements*.txt"))

    def exposed_names(self, repo_root: Path) -> set[str]:
        names: set[str] = set()
        pp = repo_root / "pyproject.toml"
        if pp.is_file():
            try:
                data = tomllib.loads(pp.read_text(encoding="utf-8"))
                proj = data.get("project", {})
                if isinstance(proj, dict) and proj.get("name"):
                    names.add(str(proj["name"]))
            except (tomllib.TOMLDecodeError, OSError):
                pass
        cfg = repo_root / "setup.cfg"
        if cfg.is_file():
            try:
                cp = configparser.ConfigParser()
                cp.read(cfg, encoding="utf-8")
                if cp.has_option("metadata", "name"):
                    names.add(cp.get("metadata", "name"))
            except (configparser.Error, OSError):
                pass
        # top-level importable packages/modules (repo root and src/)
        for base in (repo_root, repo_root / "src"):
            if not base.is_dir():
                continue
            for child in base.iterdir():
                if child.is_dir() and (child / "__init__.py").is_file():
                    names.add(child.name)
                elif child.suffix == ".py" and child.stem not in {"setup", "conftest"}:
                    names.add(child.stem)
        return names

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []
        edges += self._manifest_edges(repo_root)
        edges += self._import_edges(repo_root)
        return edges

    def _manifest_edges(self, repo_root: Path) -> list[RawEdge]:
        out: list[RawEdge] = []
        pp = repo_root / "pyproject.toml"
        if pp.is_file():
            try:
                data = tomllib.loads(pp.read_text(encoding="utf-8"))
                proj = data.get("project", {})
                deps = list(proj.get("dependencies", []) or [])
                for group in (proj.get("optional-dependencies", {}) or {}).values():
                    deps += list(group or [])
                for spec in deps:
                    name = _dep_name(str(spec))
                    if name:
                        out.append(RawEdge(name, "manifest", "pyproject.toml", None, str(spec)))
            except (tomllib.TOMLDecodeError, OSError):
                pass
        for req in sorted(repo_root.glob("requirements*.txt")):
            try:
                for i, line in enumerate(req.read_text(encoding="utf-8").splitlines(), 1):
                    s = line.strip()
                    if not s or s.startswith(("#", "-")):
                        continue
                    name = _dep_name(s)
                    if name:
                        out.append(RawEdge(name, "manifest", req.name, i, s))
            except OSError:
                pass
        return out

    def _import_edges(self, repo_root: Path) -> list[RawEdge]:
        out: list[RawEdge] = []
        for py in walk_files(repo_root, suffixes=(".py",)):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, ValueError):
                continue
            rel = py.relative_to(repo_root).as_posix()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        top = a.name.split(".")[0]
                        out.append(RawEdge(top, "import", rel, node.lineno, f"import {a.name}"))
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module:
                        top = node.module.split(".")[0]
                        out.append(RawEdge(top, "import", rel, node.lineno, f"from {node.module} import ..."))
        return out
