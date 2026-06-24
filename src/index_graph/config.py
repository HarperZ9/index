"""Configuration: .repomap.toml parsing, neutral defaults, glob translation."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PRUNE_DIRS = frozenset({
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "__pycache__", ".venv", "venv", "node_modules",
})
DEFAULT_MARKERS = (
    "README.md", "AGENTS.md", "CLAUDE.md", "pyproject.toml", "package.json",
    "Cargo.toml", "CMakeLists.txt", "Makefile", "requirements.txt",
)
PUBLIC_HOSTS = frozenset({
    "github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "git.sr.ht",
})
_KNOWN_TOP = frozenset({"rule", "scan", "privacy", "output"})


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
    omit_origin_classes: frozenset[str] = frozenset()
    portable: bool = True
    annotations: dict[str, Any] = field(default_factory=dict)

    @property
    def prune(self) -> frozenset[str]:
        return DEFAULT_PRUNE_DIRS | self.extra_prune


def default_config() -> Config:
    return Config()


def load_config(path: Path | None, root: Path) -> Config:
    if path is None:
        candidate = root / ".repomap.toml"
        if not candidate.exists():
            return default_config()
        path = candidate
    elif not path.exists():
        raise SystemExit(f"config not found: {path}")
    with path.open("rb") as handle:
        try:
            data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise SystemExit(f"{path}: invalid TOML: {exc}") from exc
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

    omit = frozenset(str(c) for c in data.get("privacy", {}).get("omit_origin_classes", []))

    output = data.get("output", {})
    portable = bool(output.get("portable", True))
    annotations = dict(output.get("annotations", {}))

    for key in data:
        if key not in _KNOWN_TOP:
            print(f"{path}: warning: unknown config key '{key}'", file=sys.stderr)

    return Config(tuple(rules), extra_prune, markers, jobs, omit, portable, annotations)
