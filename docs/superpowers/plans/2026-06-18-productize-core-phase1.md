# Productize the Core (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `workspace-repo-map` from a single personal-workspace module into a config-driven, parallel, schema-versioned tool installable by anyone.

**Architecture:** Split `map.py` into focused modules — `model` (data), `config` (.repomap.toml + neutral defaults), `classify` (ordered glob rules + remote-host fallback), `gitmeta` (subprocess + credential redaction), `scan` (discovery + parallel fan-out + assembly), `cli` (single parser). Classification is data-driven; output is schema v1 with a portable (default) / local mode switch.

**Tech Stack:** Python ≥3.11 (stdlib only — `tomllib`, `concurrent.futures`, `argparse`, `subprocess`, `re`, `hashlib`), hatchling build, pytest.

**Spec:** `docs/superpowers/specs/2026-06-18-productize-core-design.md`

## Global Constraints

- **Python floor:** `requires-python = ">=3.11"` (stdlib `tomllib`).
- **Zero runtime dependencies:** `dependencies = []`. Test extra only: `pytest>=8`.
- **Schema:** every generated map carries `schema_version = 1`.
- **Safe by default:** `[output] portable` defaults to `true`; credential/userinfo redaction in origin URLs is **always on**, both modes.
- **Determinism:** repositories are emitted sorted by path; never rely on thread completion order.
- **No operator-specific content** ships in the package (neutral defaults; example config is generic).
- **Size gates:** no file > 300 lines, no function > 50 lines.
- **Commits:** conventional-commit style, one per completed step group.

---

## File Structure

```
src/workspace_repo_map/
  __init__.py    # public API: __all__, __version__   (Task 1 minimal → Task 7 full)
  model.py       # RepoRow, Map, SCHEMA_VERSION, to_json          (Task 2)
  config.py      # Rule, Config, load_config, glob_to_regex, defaults (Task 3)
  classify.py    # classify(), remote-host fallback               (Task 4)
  gitmeta.py     # run_git, sanitize_credentials, repo_metadata    (Task 5)
  scan.py        # discover_repos, build_map, write_map            (Task 6)
  cli.py         # single argparse parser + main()                 (Task 7)
  __main__.py    # from .cli import main                           (Task 7)
  map.py         # DELETED in Task 7
tests/
  test_model.py  test_config.py  test_classify.py
  test_gitmeta.py  test_scan.py  test_cli.py
  test_workspace_repo_map.py   # DELETED in Task 7
example.repomap.toml           # generic example                  (Task 8)
```

---

### Task 1: Project setup — Python 3.11, dynamic version

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/workspace_repo_map/__init__.py`
- Test: `tests/test_version.py` (create)

**Interfaces:**
- Produces: `workspace_repo_map.__version__ == "0.2.0"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_version.py`:
```python
import workspace_repo_map


def test_version_is_0_2_0():
    assert workspace_repo_map.__version__ == "0.2.0"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_version.py -v`
Expected: FAIL — current `__init__.py` does `from .map import *` and defines no `__version__` (AttributeError).

- [ ] **Step 3: Replace `__init__.py` with a minimal version stub**

Replace the entire contents of `src/workspace_repo_map/__init__.py` with:
```python
"""Compact JSON repository inventory maps for multi-repo workspaces."""

__version__ = "0.2.0"
```
(The full public API is assembled in Task 7, once the submodules exist.)

- [ ] **Step 4: Update `pyproject.toml` for Python 3.11 + dynamic version**

In `[project]`, delete the line `version = "0.1.0"` and add `dynamic = ["version"]`. Change `requires-python = ">=3.10"` to `requires-python = ">=3.11"`. Then add a new section:
```toml
[tool.hatch.version]
path = "src/workspace_repo_map/__init__.py"
```

- [ ] **Step 5: Run it to verify it passes**

Run: `python -m pytest tests/test_version.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/workspace_repo_map/__init__.py tests/test_version.py
git commit -m "build: target Python 3.11 and single-source the version"
```

---

### Task 2: `model.py` — data classes and schema

**Files:**
- Create: `src/workspace_repo_map/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces:
  - `SCHEMA_VERSION: int = 1`
  - `RepoRow(path, class_, branch, head, origin, dirty_count, untracked_count, markers)` (frozen); `.to_json() -> dict` (maps `class_` → `"class"`, `markers` tuple → list).
  - `Map(schema_version, tool_version, generated_at, root_sha256_prefix, root, absolute_paths_included, repo_count, dirty_count, class_counts, top_level, repositories, annotations={})` (frozen); `.to_json() -> dict` (omits `root` when `None`; omits `annotations` when empty).

- [ ] **Step 1: Write the failing test**

Create `tests/test_model.py`:
```python
from workspace_repo_map.model import Map, RepoRow, SCHEMA_VERSION


def _row(**over):
    base = dict(path="public/demo", class_="public", branch="main", head="abc1234",
                origin="https://github.com/o/r.git", dirty_count=0, untracked_count=1,
                markers=("README.md",))
    base.update(over)
    return RepoRow(**base)


def test_reporow_to_json_maps_class_and_lists_markers():
    data = _row().to_json()
    assert data["class"] == "public"
    assert "class_" not in data
    assert data["markers"] == ["README.md"]


def _map(**over):
    base = dict(schema_version=SCHEMA_VERSION, tool_version="0.2.0",
                generated_at="2026-06-18T00:00:00-07:00", root_sha256_prefix="abcd",
                root=None, absolute_paths_included=False, repo_count=1, dirty_count=0,
                class_counts={"public": 1}, top_level=(), repositories=(_row(),))
    base.update(over)
    return Map(**base)


def test_map_to_json_portable_omits_root_and_empty_annotations():
    data = _map().to_json()
    assert data["schema_version"] == 1
    assert "root" not in data
    assert "annotations" not in data
    assert data["repositories"][0]["class"] == "public"


def test_map_to_json_local_includes_root_and_annotations():
    data = _map(root="C:/dev", absolute_paths_included=True,
                annotations={"operating_model": "x"}).to_json()
    assert data["root"] == "C:/dev"
    assert data["annotations"] == {"operating_model": "x"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: workspace_repo_map.model`.

- [ ] **Step 3: Write the implementation**

Create `src/workspace_repo_map/model.py`:
```python
"""Pure data model for a workspace repository map. No I/O, git, or config."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RepoRow:
    path: str
    class_: str
    branch: str
    head: str
    origin: str
    dirty_count: int
    untracked_count: int
    markers: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "class": self.class_,
            "branch": self.branch,
            "head": self.head,
            "origin": self.origin,
            "dirty_count": self.dirty_count,
            "untracked_count": self.untracked_count,
            "markers": list(self.markers),
        }


@dataclass(frozen=True)
class Map:
    schema_version: int
    tool_version: str
    generated_at: str
    root_sha256_prefix: str
    root: str | None
    absolute_paths_included: bool
    repo_count: int
    dirty_count: int
    class_counts: dict[str, int]
    top_level: tuple[dict[str, Any], ...]
    repositories: tuple[RepoRow, ...]
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "generated_at": self.generated_at,
            "root_sha256_prefix": self.root_sha256_prefix,
            "absolute_paths_included": self.absolute_paths_included,
            "repo_count": self.repo_count,
            "dirty_count": self.dirty_count,
            "class_counts": self.class_counts,
            "top_level": list(self.top_level),
            "repositories": [row.to_json() for row in self.repositories],
        }
        if self.root is not None:
            data["root"] = self.root
        if self.annotations:
            data["annotations"] = self.annotations
        return data
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/test_model.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workspace_repo_map/model.py tests/test_model.py
git commit -m "feat: add versioned data model (RepoRow, Map, schema v1)"
```

---

### Task 3: `config.py` — `.repomap.toml`, defaults, glob translation

**Files:**
- Create: `src/workspace_repo_map/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `glob_to_regex(pattern: str) -> str` — `*`→`[^/]*`, `**`→`.*`, `/**`→`(/.*)?`, literals escaped, anchored.
  - `Rule(pattern: str, class_: str)` (frozen) with compiled `.regex` (built in `__post_init__`).
  - `Config(rules, extra_prune, markers, jobs, omit_origin_classes, portable, annotations)` (frozen) with `.prune` property = `DEFAULT_PRUNE_DIRS | extra_prune`.
  - `default_config() -> Config`; `load_config(path: Path | None, root: Path) -> Config`.
  - Constants `DEFAULT_PRUNE_DIRS`, `DEFAULT_MARKERS`, `PUBLIC_HOSTS`.
- Note: config errors raise `SystemExit` with an actionable message (fail-fast on user input).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:
```python
import pytest

from workspace_repo_map.config import (
    Config, Rule, default_config, glob_to_regex, load_config,
)


def _match(pattern, path):
    import re
    return re.match(glob_to_regex(pattern), path) is not None


def test_glob_double_star_matches_lane_and_nested():
    assert _match("public/**", "public")
    assert _match("public/**", "public/demo")
    assert _match("public/**", "public/demo/sub")
    assert not _match("public/**", "publicx")


def test_glob_single_star_stays_in_segment():
    assert _match("*", "data")
    assert not _match("*", "a/b")


def test_glob_dot_prefix_rule():
    assert _match(".*", ".claude")
    assert not _match(".*", "data")


def test_default_config_is_neutral():
    cfg = default_config()
    assert cfg.rules == ()
    assert cfg.portable is True
    assert cfg.omit_origin_classes == frozenset()
    assert ".git" in cfg.prune


def test_load_config_parses_rules_scan_privacy_output(tmp_path):
    (tmp_path / ".repomap.toml").write_text(
        '[[rule]]\npattern = "public/**"\nclass = "public"\n'
        '[scan]\njobs = 4\nprune = ["vendor"]\n'
        '[privacy]\nomit_origin_classes = ["protected"]\n'
        '[output]\nportable = false\nannotations = { note = "x" }\n',
        encoding="utf-8",
    )
    cfg = load_config(None, tmp_path)
    assert cfg.rules[0].class_ == "public"
    assert cfg.rules[0].regex.match("public/demo")
    assert cfg.jobs == 4
    assert "vendor" in cfg.prune and ".git" in cfg.prune  # extends, never replaces
    assert cfg.omit_origin_classes == frozenset({"protected"})
    assert cfg.portable is False
    assert cfg.annotations == {"note": "x"}


def test_load_config_absent_file_returns_defaults(tmp_path):
    assert load_config(None, tmp_path).rules == ()


def test_missing_config_path_is_fatal(tmp_path):
    with pytest.raises(SystemExit):
        load_config(tmp_path / "nope.toml", tmp_path)


def test_rule_without_class_is_fatal(tmp_path):
    (tmp_path / ".repomap.toml").write_text('[[rule]]\npattern = "x"\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        load_config(None, tmp_path)


def test_bad_jobs_is_fatal(tmp_path):
    (tmp_path / ".repomap.toml").write_text("[scan]\njobs = 0\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_config(None, tmp_path)


def test_unknown_key_warns_not_fatal(tmp_path, capsys):
    (tmp_path / ".repomap.toml").write_text('[bogus]\nx = 1\n', encoding="utf-8")
    cfg = load_config(None, tmp_path)
    assert cfg.rules == ()
    assert "unknown config key 'bogus'" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: workspace_repo_map.config`.

- [ ] **Step 3: Write the implementation**

Create `src/workspace_repo_map/config.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workspace_repo_map/config.py tests/test_config.py
git commit -m "feat: add config-driven classification rules and neutral defaults"
```

---

### Task 4: `classify.py` — ordered rules + remote-host fallback

**Files:**
- Create: `src/workspace_repo_map/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: `Config`, `Rule.regex`, `PUBLIC_HOSTS` (Task 3).
- Produces: `classify(path: str, is_repo: bool, origin: str, config: Config) -> str`. First matching rule wins; else, for repos, the ladder `no-origin → "local"`, `public host → "public"`, else `"private"`; for non-repo entries, `"hidden"` (dot-prefixed) or `"entry"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_classify.py`:
```python
from workspace_repo_map.classify import classify
from workspace_repo_map.config import Config, Rule


def test_first_matching_rule_wins():
    cfg = Config(rules=(Rule("public/**", "public"), Rule("**", "workspace")))
    assert classify("public/demo", True, "", cfg) == "public"
    assert classify("other/repo", True, "", cfg) == "workspace"


def test_fallback_ladder_for_repos():
    cfg = Config()
    assert classify("x", True, "", cfg) == "local"
    assert classify("x", True, "https://github.com/o/r.git", cfg) == "public"
    assert classify("x", True, "git@github.com:o/r.git", cfg) == "public"
    assert classify("x", True, "https://git.example.com/o/r.git", cfg) == "private"


def test_root_entry_fallback():
    cfg = Config()
    assert classify(".cache", False, "", cfg) == "hidden"
    assert classify("notes", False, "", cfg) == "entry"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_classify.py -v`
Expected: FAIL — `ModuleNotFoundError: workspace_repo_map.classify`.

- [ ] **Step 3: Write the implementation**

Create `src/workspace_repo_map/classify.py`:
```python
"""Pure classification: ordered glob rules, then a remote-host fallback."""

from __future__ import annotations

from urllib.parse import urlsplit

from .config import PUBLIC_HOSTS, Config


def _remote_host(origin: str) -> str | None:
    if not origin:
        return None
    if "://" not in origin and "@" in origin and ":" in origin:
        # scp-like SSH form: git@github.com:owner/repo.git
        return origin.split("@", 1)[1].split(":", 1)[0] or None
    return urlsplit(origin).hostname


def classify(path: str, is_repo: bool, origin: str, config: Config) -> str:
    for rule in config.rules:
        if rule.regex.match(path):
            return rule.class_
    if is_repo:
        host = _remote_host(origin)
        if host is None:
            return "local"
        return "public" if host in PUBLIC_HOSTS else "private"
    name = path.rsplit("/", 1)[-1]
    return "hidden" if name.startswith(".") else "entry"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_classify.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workspace_repo_map/classify.py tests/test_classify.py
git commit -m "feat: add ordered-rule classifier with remote-host fallback"
```

---

### Task 5: `gitmeta.py` — subprocess layer + always-on redaction

**Files:**
- Create: `src/workspace_repo_map/gitmeta.py`
- Test: `tests/test_gitmeta.py`

**Interfaces:**
- Produces:
  - `run_git(repo: Path, args: list[str]) -> str` — `timeout=20`, `check=False`, returns stripped stdout or `""`.
  - `sanitize_credentials(origin: str) -> str` — redacts `https://user@`→`https://<redacted>@` and `token=…`/`password=…`/`secret=…`/`api_key=…` query material. Host-preserving.
  - `repo_metadata(repo: Path) -> dict` — keys `branch`, `head`, `origin` (credential-redacted), `dirty_count`, `untracked_count`. A repo with no git output degrades to `branch`/`head` = `"unknown"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gitmeta.py`:
```python
import subprocess
from pathlib import Path

from workspace_repo_map.gitmeta import repo_metadata, run_git, sanitize_credentials


def test_sanitize_redacts_userinfo_but_keeps_host():
    assert sanitize_credentials("https://tok@github.com/o/r.git") == \
        "https://<redacted>@github.com/o/r.git"


def test_sanitize_redacts_secret_query():
    assert sanitize_credentials("https://example.com/r.git?token=abc") == \
        "https://example.com/r.git?token=<redacted>"


def test_sanitize_leaves_ssh_user_alone():
    assert sanitize_credentials("git@github.com:o/r.git") == "git@github.com:o/r.git"


def test_repo_metadata_degrades_on_non_repo(tmp_path: Path):
    meta = repo_metadata(tmp_path)  # not a git repo -> all git calls return ""
    assert meta["branch"] == "unknown"
    assert meta["head"] == "unknown"
    assert meta["dirty_count"] == 0


def test_repo_metadata_reads_real_repo(tmp_path: Path):
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.t"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"],
                   check=True, capture_output=True)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "i"], check=True,
                   capture_output=True)
    meta = repo_metadata(tmp_path)
    assert meta["branch"] == "main"
    assert meta["head"] != "unknown"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_gitmeta.py -v`
Expected: FAIL — `ModuleNotFoundError: workspace_repo_map.gitmeta`.

- [ ] **Step 3: Write the implementation**

Create `src/workspace_repo_map/gitmeta.py`:
```python
"""Git subprocess access and always-on credential redaction."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

_USERINFO = re.compile(r"(?i)(https?://)[^/@]+@")
_SECRET_QUERY = re.compile(r"(?i)\b(token|password|secret|api[_-]?key)=([^@\s]+)")


def sanitize_credentials(origin: str) -> str:
    clean = _USERINFO.sub(r"\1<redacted>@", origin)
    return _SECRET_QUERY.sub(r"\1=<redacted>", clean)


def run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True, capture_output=True, timeout=20, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def repo_metadata(repo: Path) -> dict[str, Any]:
    status = run_git(repo, ["status", "--porcelain=v1"]).splitlines()
    untracked = sum(1 for line in status if line.startswith("??"))
    dirty = sum(1 for line in status if line and not line.startswith("??"))
    branch = (
        run_git(repo, ["branch", "--show-current"])
        or run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
        or "unknown"
    )
    head = run_git(repo, ["rev-parse", "--short=7", "HEAD"]) or "unknown"
    origin = sanitize_credentials(run_git(repo, ["config", "--get", "remote.origin.url"]) or "")
    return {
        "branch": branch,
        "head": head,
        "origin": origin,
        "dirty_count": dirty,
        "untracked_count": untracked,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_gitmeta.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workspace_repo_map/gitmeta.py tests/test_gitmeta.py
git commit -m "feat: add git metadata layer with always-on credential redaction"
```

---

### Task 6: `scan.py` — discovery, parallel fan-out, assembly

**Files:**
- Create: `src/workspace_repo_map/scan.py`
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: `Config` (Task 3), `classify` (Task 4), `repo_metadata` (Task 5), `Map`/`RepoRow`/`SCHEMA_VERSION` (Task 2).
- Produces:
  - `discover_repos(root: Path, config: Config) -> list[Path]` — `os.walk`, prunes `config.prune`, sorted by relative POSIX path.
  - `build_map(root: Path, config: Config, tool_version: str) -> Map` — parallel `repo_metadata`, applies `classify`, applies portability (relative + sha256 root vs absolute + `root`), applies `omit_origin_classes`, assembles `class_counts` and `top_level`. A per-repo failure degrades to an `"unknown"` row (spec §9), never crashes the scan.
  - `write_map(root, config, tool_version, output: Path) -> Map`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scan.py`:
```python
from pathlib import Path

from workspace_repo_map.config import Config, Rule
from workspace_repo_map.scan import build_map, discover_repos


def _make_repo(path: Path):
    (path / ".git").mkdir(parents=True)


def test_discover_prunes_and_sorts(tmp_path: Path):
    _make_repo(tmp_path / "public" / "b")
    _make_repo(tmp_path / "public" / "a")
    (tmp_path / "node_modules" / "pkg" / ".git").mkdir(parents=True)
    found = [p.relative_to(tmp_path).as_posix() for p in discover_repos(tmp_path, Config())]
    assert found == ["public/a", "public/b"]  # sorted; node_modules pruned


def test_build_map_portable_omits_absolute_paths(tmp_path: Path):
    _make_repo(tmp_path / "public" / "demo")
    result = build_map(tmp_path, Config(rules=(Rule("public/**", "public"),)), "0.2.0")
    encoded = str(result.to_json())
    assert result.absolute_paths_included is False
    assert result.root is None
    assert str(tmp_path) not in encoded
    assert result.repositories[0].path == "public/demo"
    assert result.class_counts == {"public": 1}


def test_build_map_local_includes_absolute_root(tmp_path: Path):
    _make_repo(tmp_path / "demo")
    result = build_map(tmp_path, Config(portable=False), "0.2.0")
    assert result.absolute_paths_included is True
    assert result.root == str(tmp_path.resolve())
    assert result.repositories[0].path == str((tmp_path / "demo").resolve())


def test_omit_origin_classes_blanks_origin(tmp_path: Path):
    _make_repo(tmp_path / "protected" / "secret")
    cfg = Config(rules=(Rule("protected/**", "protected"),),
                 omit_origin_classes=frozenset({"protected"}))
    result = build_map(tmp_path, cfg, "0.2.0")
    assert result.repositories[0].origin == ""


def test_build_map_degrades_when_a_repo_errors(tmp_path: Path, monkeypatch, capsys):
    _make_repo(tmp_path / "demo")
    import workspace_repo_map.scan as scan_mod
    def _boom(repo):
        raise RuntimeError("boom")
    monkeypatch.setattr(scan_mod, "repo_metadata", _boom)
    result = build_map(tmp_path, Config(), "0.2.0")
    assert result.repo_count == 1
    assert result.repositories[0].branch == "unknown"
    assert result.repositories[0].class_ == "unknown"
    assert "failed to scan" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_scan.py -v`
Expected: FAIL — `ModuleNotFoundError: workspace_repo_map.scan`.

- [ ] **Step 3: Write the implementation**

Create `src/workspace_repo_map/scan.py`:
```python
"""Discovery, parallel git fan-out, and map assembly."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from .classify import classify
from .config import Config
from .gitmeta import repo_metadata
from .model import SCHEMA_VERSION, Map, RepoRow


def discover_repos(root: Path, config: Config) -> list[Path]:
    prune = config.prune
    repos: set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if ".git" in dirnames or ".git" in filenames:
            repos.add(current)
        dirnames[:] = [name for name in dirnames if name not in prune]
    return sorted(repos, key=lambda p: p.relative_to(root).as_posix().lower())


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return path.name


def _repo_row(repo: Path, root: Path, config: Config) -> RepoRow:
    meta = repo_metadata(repo)
    rel = _relative(repo, root)
    class_ = classify(rel, True, meta["origin"], config)
    origin = "" if class_ in config.omit_origin_classes else meta["origin"]
    path = rel if config.portable else str(repo)
    markers = tuple(name for name in config.markers if (repo / name).exists())
    return RepoRow(
        path=path, class_=class_, branch=meta["branch"], head=meta["head"],
        origin=origin, dirty_count=meta["dirty_count"],
        untracked_count=meta["untracked_count"], markers=markers,
    )


def _safe_repo_row(repo: Path, root: Path, config: Config) -> RepoRow:
    # Spec §9: one repo's failure must degrade to a row, never crash the scan.
    try:
        return _repo_row(repo, root, config)
    except Exception as exc:
        rel = _relative(repo, root)
        print(f"warning: failed to scan {rel}: {exc}", file=sys.stderr)
        return RepoRow(
            path=(rel if config.portable else str(repo)), class_="unknown",
            branch="unknown", head="unknown", origin="", dirty_count=0,
            untracked_count=0, markers=(),
        )


def _top_level(root: Path, config: Config) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if path.name == ".git":
            continue
        stat = path.stat()
        entries.append({
            "name": path.name,
            "kind": "directory" if path.is_dir() else "file",
            "class": classify(path.name, False, "", config),
            "bytes": None if path.is_dir() else stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        })
    return entries


def build_map(root: Path, config: Config, tool_version: str) -> Map:
    root = root.resolve()
    repo_paths = discover_repos(root, config)
    # Executor.map preserves submission order, so rows stay in discovery (sorted) order
    # regardless of thread completion order — output is deterministic.
    with ThreadPoolExecutor(max_workers=config.jobs) as pool:
        rows = list(pool.map(lambda p: _safe_repo_row(p, root, config), repo_paths))
    class_counts: dict[str, int] = {}
    for row in rows:
        class_counts[row.class_] = class_counts.get(row.class_, 0) + 1
    return Map(
        schema_version=SCHEMA_VERSION,
        tool_version=tool_version,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        root_sha256_prefix=hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16],
        root=None if config.portable else str(root),
        absolute_paths_included=not config.portable,
        repo_count=len(rows),
        dirty_count=sum(row.dirty_count for row in rows),
        class_counts=class_counts,
        top_level=tuple(_top_level(root, config)),
        repositories=tuple(rows),
        annotations=dict(config.annotations),
    )


def write_map(root: Path, config: Config, tool_version: str, output: Path) -> Map:
    data = build_map(root, config, tool_version)
    output.write_text(json.dumps(data.to_json(), indent=2) + "\n", encoding="utf-8")
    return data
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_scan.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workspace_repo_map/scan.py tests/test_scan.py
git commit -m "feat: add parallel scan with portable/local assembly"
```

---

### Task 7: `cli.py`, public API, and retiring `map.py`

**Files:**
- Create: `src/workspace_repo_map/cli.py`
- Modify: `src/workspace_repo_map/__init__.py` (full public API)
- Modify: `src/workspace_repo_map/__main__.py`
- Delete: `src/workspace_repo_map/map.py`
- Delete: `tests/test_workspace_repo_map.py` (its assertions describe the retired single-module schema)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config` (Task 3), `build_map`/`write_map` (Task 6), `__version__` (Task 1).
- Produces: `build_parser()`, `main(argv: list[str] | None = None) -> int`; package exports `__all__`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:
```python
import json

import pytest

from workspace_repo_map.cli import main


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "0.2.0" in capsys.readouterr().out


def test_json_to_stdout(tmp_path, capsys):
    (tmp_path / "demo" / ".git").mkdir(parents=True)
    assert main(["--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1


def test_writes_default_output(tmp_path):
    (tmp_path / "demo" / ".git").mkdir(parents=True)
    assert main(["--root", str(tmp_path)]) == 0
    assert (tmp_path / "WORKSPACE-REPO-MAP.json").exists()


def test_missing_config_is_fatal(tmp_path):
    with pytest.raises(SystemExit):
        main(["--root", str(tmp_path), "--config", str(tmp_path / "nope.toml")])


def test_public_api_surface():
    import workspace_repo_map as pkg
    for name in ("build_map", "Map", "RepoRow", "Config", "Rule", "load_config", "classify"):
        assert name in pkg.__all__
        assert hasattr(pkg, name)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: workspace_repo_map.cli`.

- [ ] **Step 3: Write `cli.py`**

Create `src/workspace_repo_map/cli.py`:
```python
"""Single command-line entry point."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from . import __version__
from .config import load_config
from .scan import build_map, write_map


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-repo-map",
        description="Compact JSON repository inventory maps for multi-repo workspaces.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Workspace root. Defaults to the current directory.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path. Defaults to <root>/WORKSPACE-REPO-MAP.json.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    parser.add_argument("--config", type=Path, default=None, help="Path to .repomap.toml.")
    parser.add_argument("--jobs", type=int, default=None, help="Override worker count.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    config = load_config(args.config, root)
    if args.jobs is not None:
        if args.jobs < 1:
            raise SystemExit("--jobs must be a positive integer")
        config = replace(config, jobs=args.jobs)
    if args.json:
        data = build_map(root, config, __version__)
        print(json.dumps(data.to_json(), indent=2))
    else:
        output = args.output.resolve() if args.output else root / "WORKSPACE-REPO-MAP.json"
        data = write_map(root, config, __version__, output)
        print(f"wrote {output}")
        print(f"repos={data.repo_count} dirty={data.dirty_count}")
    return 0
```

- [ ] **Step 4: Write the full `__init__.py` public API**

Replace the entire contents of `src/workspace_repo_map/__init__.py` with:
```python
"""Compact JSON repository inventory maps for multi-repo workspaces."""

from __future__ import annotations

from .classify import classify
from .config import Config, Rule, default_config, load_config
from .model import SCHEMA_VERSION, Map, RepoRow
from .scan import build_map, discover_repos, write_map

__version__ = "0.2.0"
__all__ = [
    "build_map", "write_map", "discover_repos",
    "Map", "RepoRow", "SCHEMA_VERSION",
    "Config", "Rule", "load_config", "default_config",
    "classify", "__version__",
]
```

- [ ] **Step 5: Update `__main__.py`**

Replace the entire contents of `src/workspace_repo_map/__main__.py` with:
```python
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Delete the retired module and its test**

```bash
git rm src/workspace_repo_map/map.py tests/test_workspace_repo_map.py
```

- [ ] **Step 7: Run the full suite to verify everything passes**

Run: `python -m pytest -v`
Expected: PASS — all of `test_version`, `test_model`, `test_config`, `test_classify`, `test_gitmeta`, `test_scan`, `test_cli`. No import of the deleted `map` module remains.

- [ ] **Step 8: Verify the CLI end-to-end**

Run: `python -m workspace_repo_map --root . --json`
Expected: prints JSON with `"schema_version": 1`.

- [ ] **Step 9: Commit**

```bash
git add src/workspace_repo_map/cli.py src/workspace_repo_map/__init__.py \
        src/workspace_repo_map/__main__.py tests/test_cli.py
git commit -m "feat: unify the CLI, define the public API, retire map.py"
```

---

### Task 8: Packaging, example config, and docs

**Files:**
- Create: `example.repomap.toml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_example_config.py`

**Interfaces:**
- Consumes: `load_config` (Task 3). The shipped example must parse cleanly.

- [ ] **Step 1: Write the failing test**

Create `tests/test_example_config.py`:
```python
from pathlib import Path

from workspace_repo_map.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_example_config_parses():
    cfg = load_config(REPO_ROOT / "example.repomap.toml", REPO_ROOT)
    assert cfg.rules  # has at least one rule
    assert all(rule.regex for rule in cfg.rules)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_example_config.py -v`
Expected: FAIL — `SystemExit: config not found` (file does not exist yet).

- [ ] **Step 3: Create `example.repomap.toml` (generic, non-personal)**

Create `example.repomap.toml`:
```toml
# Example workspace-repo-map configuration. Copy to <workspace-root>/.repomap.toml.
# Rules match each repo's workspace-relative path; first match wins. With no rule
# match, repos fall back to a remote-host heuristic (local / public / private).

[[rule]]
pattern = "oss/**"
class   = "public"

[[rule]]
pattern = "work/**"
class   = "internal"

[scan]
jobs    = 16
prune   = ["vendor", "target"]   # added to the built-in safety set

[privacy]
omit_origin_classes = ["internal"]

[output]
portable = true
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_example_config.py -v`
Expected: PASS.

- [ ] **Step 5: Update `README.md`**

Bump the version badge from `version-0.1.0` to `version-0.2.0` (the python badge already reads `3.11%2B` — leave it). Replace the "Usage" section with:
````markdown
## Usage

```bash
workspace-repo-map --root . --output WORKSPACE-REPO-MAP.json
workspace-repo-map --json
```

Classification is driven by an optional `.repomap.toml` at the workspace root (see
`example.repomap.toml`). With no config, repos are classified by a neutral remote-host
heuristic: `local` (no remote), `public` (origin on a public host), or `private`. Here
`public` means "origin is on a public code-hosting platform" — a heuristic, not a
guarantee of visibility.
````

- [ ] **Step 6: Update `CHANGELOG.md`**

Add this entry above the `## 0.1.0` section:
```markdown
## 0.2.0 - 2026-06-18

- Config-driven classification via optional `.repomap.toml` (ordered path-glob rules,
  neutral remote-host fallback). Personal taxonomy moves to user config.
- Unifies the CLI into a single argument parser; removes the duplicate.
- Adds a stable public API (`__all__`, `__version__`) and a versioned output
  (`schema_version: 1`); drops the duplicated `relative` field and protected-specific
  counts in favor of generic `class_counts`.
- Parallelizes per-repo git calls; output remains deterministic.
- Adds a portable (default) / local output mode and an `annotations` passthrough.
- Raises the Python floor to 3.11 (stdlib `tomllib`); runtime dependencies stay empty.
```

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (all tests).

- [ ] **Step 8: Commit**

```bash
git add example.repomap.toml tests/test_example_config.py README.md CHANGELOG.md
git commit -m "docs: ship example config and document 0.2.0"
```

---

## Self-Review

Run after completing all tasks (or before execution, to validate the plan):

**1. Spec coverage** — every spec section maps to a task:
- §4 modules → Tasks 2–7 (one module each). §4.3 concurrency → Task 6.
- §5 config/classification → Tasks 3–4; §5.8 portable/local → Task 6 (build/assembly) + Task 3 (parsing).
- §6 schema v1 → Task 2 + Task 6. §7 CLI → Task 7. §8 public API → Task 7.
- §9 error handling → Tasks 3 (fatal config), 5 (degraded rows), 7 (unreadable root).
- §10 testing → per-task test files. §12 versioning/docs → Tasks 1 + 8.
- §1 `_skip_generated_tree` removal → Task 6 (`discover_repos` has no scratch/venvs special-case).

**2. Placeholder scan** — no "TBD"/"add error handling"/"similar to Task N"; every code step shows complete code.

**3. Type consistency** — `classify(path, is_repo, origin, config)` is defined in Task 4 and called identically in Task 6. `build_map(root, config, tool_version)` defined in Task 6, called in Task 7. `Config`/`Rule`/`Map`/`RepoRow` field names match across Tasks 2–7.

---

## Phase 2

Workspace reconciliation (retire `refresh_workspace_repo_map.py`, drive the live map via this
tool in local mode) is a **separate plan**, gated on this one shipping. Spec:
`C:\dev\docs\superpowers\specs\2026-06-18-workspace-repomap-reconciliation-design.md`.
