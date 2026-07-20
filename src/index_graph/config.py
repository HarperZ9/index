"""Configuration: .index.toml parsing, neutral defaults, glob translation."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .arch.criteria import ArchitectureCriteria, parse_architecture

DEFAULT_PRUNE_DIRS = frozenset({
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "__pycache__", ".venv", "venv", "venvs", "env",
    "node_modules", "site-packages", ".tox", ".eggs",
    "build", "dist", ".cache", ".playwright-mcp",
    ".warden-safe-cache", ".next", ".turbo",
    "target", "coverage", ".coverage", ".nyc_output",
    ".parcel-cache", ".svelte-kit", ".angular", ".expo",
    ".gradle", ".idea", ".vscode", ".yarn", ".pnpm-store",
    ".terraform", "out",
})
DEFAULT_MARKERS = (
    "README.md", "AGENTS.md", "CLAUDE.md", "pyproject.toml", "package.json",
    "Cargo.toml", "CMakeLists.txt", "Makefile", "requirements.txt",
)
PUBLIC_HOSTS = frozenset({
    "github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "git.sr.ht",
})
_KNOWN_TOP = frozenset({"rule", "scan", "privacy", "output", "architecture"})


def _default_jobs() -> int:
    return min(32, (os.cpu_count() or 4) * 5)


def glob_to_regex(pattern: str) -> str:
    """Translate a path glob to an anchored regex.

    `*` matches within a segment, `**` across segments, `/**` makes the
    separator optional so `public/**` also matches `public`.
    """
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern.startswith("/**", i):
            out.append("(/.*)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return "^" + "".join(out) + "$"


@dataclass(frozen=True)
class Rule:
    pattern: str
    class_: str
    regex: re.Pattern = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "regex", re.compile(glob_to_regex(self.pattern)))


@dataclass(frozen=True)
class Config:
    rules: tuple[Rule, ...] = ()
    extra_prune: frozenset[str] = frozenset()
    markers: tuple[str, ...] = DEFAULT_MARKERS
    jobs: int = field(default_factory=_default_jobs)
    descend_into_repos: bool = False
    include_root_repo: bool = False
    omit_origin_classes: frozenset[str] = frozenset()
    portable: bool = True
    annotations: dict[str, Any] = field(default_factory=dict)
    architecture: ArchitectureCriteria = field(default_factory=ArchitectureCriteria)

    @property
    def prune(self) -> frozenset[str]:
        return DEFAULT_PRUNE_DIRS | self.extra_prune


def default_config() -> Config:
    return Config()


def load_config(path: Path | None, root: Path) -> Config:
    if path is None:
        candidates = (root / ".index.toml", root / ".repomap.toml")
        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            return default_config()
    elif not path.exists():
        raise SystemExit(f"config not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")  # tolerate BOM and legacy bytes
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"{path}: invalid TOML: {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"{path}: cannot read: {exc}") from exc
    return _build_config(data, path)


def _build_config(data: dict[str, Any], path: Path) -> Config:
    rules: list[Rule] = []
    for idx, item in enumerate(data.get("rule", [])):
        if "pattern" not in item or "class" not in item:
            raise SystemExit(f"{path}: rule[{idx}] requires 'pattern' and 'class'")
        rules.append(Rule(str(item["pattern"]), str(item["class"])))

    scan = data.get("scan", {})
    jobs = scan.get("jobs", _default_jobs())
    if not isinstance(jobs, int) or jobs < 1:
        raise SystemExit(f"{path}: [scan] jobs must be a positive integer")
    extra_prune = frozenset(str(d) for d in scan.get("prune", []))
    markers = tuple(scan["markers"]) if "markers" in scan else DEFAULT_MARKERS
    descend_into_repos = scan.get("descend_into_repos", False)
    if not isinstance(descend_into_repos, bool):
        raise SystemExit(f"{path}: [scan] descend_into_repos must be a boolean")
    include_root_repo = scan.get("include_root_repo", False)
    if not isinstance(include_root_repo, bool):
        raise SystemExit(f"{path}: [scan] include_root_repo must be a boolean")

    omit = frozenset(str(c) for c in data.get("privacy", {}).get("omit_origin_classes", []))

    output = data.get("output", {})
    portable = bool(output.get("portable", True))
    annotations = dict(output.get("annotations", {}))

    architecture = parse_architecture(data.get("architecture", {}))

    for key in data:
        if key not in _KNOWN_TOP:
            print(f"{path}: warning: unknown config key '{key}'", file=sys.stderr)

    return Config(
        rules=tuple(rules),
        extra_prune=extra_prune,
        markers=markers,
        jobs=jobs,
        descend_into_repos=descend_into_repos,
        include_root_repo=include_root_repo,
        omit_origin_classes=omit,
        portable=portable,
        annotations=annotations,
        architecture=architecture,
    )
