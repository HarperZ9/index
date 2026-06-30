# Repo-level Dependency Graph + Context Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an inference engine to `workspace-repo-map` that derives a repo-level dependency graph from real code (Python + JS/TS), assigns topology-derived structural roles, and renders a synthesis context pack -- every edge carrying its evidence.

**Architecture:** Two new internally-isolated module groups inside the existing package -- `graph/` (resolvers → edges → roles → build) and `context/` (pack renderer) -- plus two new CLI subcommands (`graph`, `context`). The sensor is untouched; the default bare invocation still writes the map.

**Tech Stack:** Python 3.11+, stdlib only (`tomllib`, `json`, `ast`, `re`, `configparser`, `argparse`, `pathlib`, `dataclasses`, `typing`). `pytest` for tests.

## Global Constraints

- Python floor: **3.11** (use `tomllib`, PEP 604 `X | None`).
- **Zero new runtime dependencies.** `pip install workspace-repo-map` must still pull nothing. `pytest>=8` stays the only optional test dep.
- **No edge may exist with an empty `signals` tuple** -- every dependency edge is witnessed.
- **No editorializing** -- the pack renderer emits only data fields and evidence; no hardcoded interpretive sentences.
- **Fail-closed, never fabricate** -- malformed manifests / unreadable files produce a warning and omission, never a crash and never an invented edge.
- Follow existing repo conventions: `from __future__ import annotations`, frozen dataclasses for pure data, `src/` layout, `pytest -q`, tests under `tests/`.
- Commit message style: `feat:` / `test:` / `docs:` prefixes; end commits with the `Co-Authored-By` trailer used in this repo.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/workspace_repo_map/graph/__init__.py` | Package marker; re-export `build_graph`, `DependencyGraph`. |
| `src/workspace_repo_map/graph/resolvers/__init__.py` | Package marker; `ALL_RESOLVERS` registry. |
| `src/workspace_repo_map/graph/resolvers/base.py` | `RawEdge` dataclass, `Resolver` Protocol, `normalize_name`. |
| `src/workspace_repo_map/graph/resolvers/python.py` | `PythonResolver` -- pyproject/requirements/setup.cfg + `.py` import scan. |
| `src/workspace_repo_map/graph/resolvers/javascript.py` | `JavaScriptResolver` -- package.json + JS/TS import scan. |
| `src/workspace_repo_map/graph/edges.py` | `Signal`, `Edge`, `build_index`, `resolve_edges`. |
| `src/workspace_repo_map/graph/roles.py` | `structural_salience`, `salience_audit`, `derive_roles`. |
| `src/workspace_repo_map/graph/build.py` | `RepoNode`, `DependencyGraph`, `detect_markers`, `build_graph`. |
| `src/workspace_repo_map/context/__init__.py` | Package marker. |
| `src/workspace_repo_map/context/pack.py` | `render_text`, `to_json`, `closure`, `subgraph`. |
| `src/workspace_repo_map/cli.py` | MODIFY -- `map`/`graph`/`context` subcommands + backward compat. |
| `tests/fixtures/` | Synthetic Python + JS/TS repo trees. |
| `tests/test_resolver_python.py` … `tests/test_cli_subcommands.py` | One test module per task. |

---

## Task 1: Python resolver (and the resolver seam)

**Files:**
- Create: `src/workspace_repo_map/graph/__init__.py`
- Create: `src/workspace_repo_map/graph/resolvers/__init__.py`
- Create: `src/workspace_repo_map/graph/resolvers/base.py`
- Create: `src/workspace_repo_map/graph/resolvers/python.py`
- Create: `tests/fixtures/py_app/` and `tests/fixtures/py_lib/` (synthetic)
- Test: `tests/test_resolver_python.py`

**Interfaces:**
- Produces: `RawEdge(target_name: str, signal: str, evidence_file: str, evidence_line: int | None, raw_spec: str)` (frozen). `normalize_name(name: str) -> str` (lowercase, `_`→`-`, strip surrounding whitespace; preserves a leading `@scope/`). `Resolver` Protocol with `name: str`, `matches(repo_root: Path) -> bool`, `exposed_names(repo_root: Path) -> set[str]`, `raw_edges(repo_root: Path) -> list[RawEdge]`. `PythonResolver` implementing it.

- [ ] **Step 1: Create package markers**

`src/workspace_repo_map/graph/__init__.py`:
```python
"""Repo-level dependency inference engine."""
```
`src/workspace_repo_map/graph/resolvers/__init__.py`:
```python
"""Per-ecosystem dependency resolvers."""
```

- [ ] **Step 2: Write the failing test for the Python fixture**

Create fixtures first:

`tests/fixtures/py_lib/pyproject.toml`:
```toml
[project]
name = "py-lib"
version = "0.1.0"
dependencies = ["requests>=2", "rich"]
```
`tests/fixtures/py_lib/py_lib/__init__.py`:
```python
import requests
```
`tests/fixtures/py_app/pyproject.toml`:
```toml
[project]
name = "py-app"
version = "0.1.0"
dependencies = ["py-lib"]

[project.scripts]
py-app = "py_app.cli:main"
```
`tests/fixtures/py_app/py_app/cli.py`:
```python
from py_lib import thing
import os

def main():
    return thing, os
```

`tests/test_resolver_python.py`:
```python
from __future__ import annotations

from pathlib import Path

from workspace_repo_map.graph.resolvers.base import normalize_name
from workspace_repo_map.graph.resolvers.python import PythonResolver

FIX = Path(__file__).parent / "fixtures"


def test_normalize_name():
    assert normalize_name("My_Pkg") == "my-pkg"
    assert normalize_name("  rich ") == "rich"


def test_matches_python_repo():
    assert PythonResolver().matches(FIX / "py_lib") is True
    assert PythonResolver().matches(FIX / "py_app") is True


def test_exposed_names_includes_dist_and_packages():
    names = PythonResolver().exposed_names(FIX / "py_lib")
    norm = {normalize_name(n) for n in names}
    assert "py-lib" in norm  # dist name


def test_raw_edges_manifest_and_import():
    edges = PythonResolver().raw_edges(FIX / "py_app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("py-lib", "manifest") in by
    assert ("py_lib", "import") in by
    # evidence is always populated
    assert all(e.evidence_file for e in edges)
    imp = next(e for e in edges if e.signal == "import" and e.target_name == "py_lib")
    assert imp.evidence_line is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /c/dev/worktrees/wrm-context && python -m pytest tests/test_resolver_python.py -q`
Expected: FAIL with `ModuleNotFoundError: workspace_repo_map.graph.resolvers.base`.

- [ ] **Step 4: Implement `base.py`**

```python
"""Resolver seam: the generic interface every ecosystem implements."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RawEdge:
    target_name: str          # name imported/declared, e.g. "requests", "@scope/pkg"
    signal: str               # "manifest" | "import"
    evidence_file: str        # repo-relative path of the witnessing file
    evidence_line: int | None # line number where cheaply known, else None
    raw_spec: str             # literal text witnessed (dep spec or import line)


def normalize_name(name: str) -> str:
    """Lowercase and unify '_'/'-' so a dist name matches an import name."""
    return name.strip().lower().replace("_", "-")


class Resolver(Protocol):
    name: str

    def matches(self, repo_root: Path) -> bool: ...
    def exposed_names(self, repo_root: Path) -> set[str]: ...
    def raw_edges(self, repo_root: Path) -> list[RawEdge]: ...
```

- [ ] **Step 5: Implement `python.py`**

```python
"""Python ecosystem resolver: manifests + AST import scan."""
from __future__ import annotations

import ast
import configparser
import re
import tomllib
from pathlib import Path

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
        for py in repo_root.rglob("*.py"):
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_resolver_python.py -q`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add src/workspace_repo_map/graph tests/fixtures/py_app tests/fixtures/py_lib tests/test_resolver_python.py
git commit -m "feat: Python resolver and the generic resolver seam"
```

---

## Task 2: JavaScript/TypeScript resolver

**Files:**
- Create: `src/workspace_repo_map/graph/resolvers/javascript.py`
- Modify: `src/workspace_repo_map/graph/resolvers/__init__.py` (add `ALL_RESOLVERS`)
- Create: `tests/fixtures/js_app/`, `tests/fixtures/js_lib/`
- Test: `tests/test_resolver_javascript.py`

**Interfaces:**
- Consumes: `RawEdge`, `Resolver` from Task 1.
- Produces: `JavaScriptResolver` implementing `Resolver`. `ALL_RESOLVERS: tuple[Resolver, ...]` in `resolvers/__init__.py` (instances of every resolver).

- [ ] **Step 1: Write fixtures + failing test**

`tests/fixtures/js_lib/package.json`:
```json
{ "name": "@acme/js-lib", "version": "0.1.0", "dependencies": { "lodash": "^4" } }
```
`tests/fixtures/js_lib/index.js`:
```javascript
import _ from "lodash";
export const x = _;
```
`tests/fixtures/js_app/package.json`:
```json
{ "name": "js-app", "version": "0.1.0", "dependencies": { "@acme/js-lib": "^0.1.0" } }
```
`tests/fixtures/js_app/src/main.ts`:
```typescript
import { x } from "@acme/js-lib";
const y = require("./local");
export default x;
```

`tests/test_resolver_javascript.py`:
```python
from __future__ import annotations

from pathlib import Path

from workspace_repo_map.graph.resolvers import ALL_RESOLVERS
from workspace_repo_map.graph.resolvers.javascript import JavaScriptResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed_name():
    r = JavaScriptResolver()
    assert r.matches(FIX / "js_app") is True
    assert "@acme/js-lib" in r.exposed_names(FIX / "js_lib")


def test_raw_edges_manifest_and_import_skip_relative():
    edges = JavaScriptResolver().raw_edges(FIX / "js_app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("@acme/js-lib", "manifest") in by
    assert ("@acme/js-lib", "import") in by
    # relative require("./local") is intra-repo -> never emitted
    assert all(not e.target_name.startswith(".") for e in edges)


def test_registry_contains_both_resolvers():
    names = {r.name for r in ALL_RESOLVERS}
    assert {"python", "javascript"} <= names
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_resolver_javascript.py -q`
Expected: FAIL (`ModuleNotFoundError` / `ImportError` for `javascript`).

- [ ] **Step 3: Implement `javascript.py`**

```python
"""JavaScript/TypeScript resolver: package.json + conservative import scan."""
from __future__ import annotations

import json
import re
from pathlib import Path

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
        for src in repo_root.rglob("*"):
            if src.suffix not in _EXTS or "node_modules" in src.parts:
                continue
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
```

- [ ] **Step 4: Update the registry**

`src/workspace_repo_map/graph/resolvers/__init__.py`:
```python
"""Per-ecosystem dependency resolvers."""
from .javascript import JavaScriptResolver
from .python import PythonResolver

ALL_RESOLVERS = (PythonResolver(), JavaScriptResolver())
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_resolver_javascript.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/workspace_repo_map/graph/resolvers tests/fixtures/js_app tests/fixtures/js_lib tests/test_resolver_javascript.py
git commit -m "feat: JavaScript/TypeScript resolver + resolver registry"
```

---

## Task 3: Edge resolution

**Files:**
- Create: `src/workspace_repo_map/graph/edges.py`
- Test: `tests/test_edges.py`

**Interfaces:**
- Consumes: `RawEdge`, `normalize_name` from Task 1.
- Produces:
  - `Signal(kind: str, evidence_file: str, evidence_line: int | None, raw_spec: str)` (frozen).
  - `Edge(from_repo: str, to_repo: str | None, target_name: str, external: bool, confidence: str, signals: tuple[Signal, ...])` (frozen).
  - `build_index(exposed: dict[str, set[str]]) -> dict[str, list[str]]` -- normalized name → list of repos exposing it.
  - `resolve_edges(repo_raw: dict[str, list[RawEdge]], index: dict[str, list[str]], short_len: int = 2) -> tuple[list[Edge], list[str]]` -- returns (edges, warnings).

- [ ] **Step 1: Write the failing test**

`tests/test_edges.py`:
```python
from __future__ import annotations

from workspace_repo_map.graph.edges import Edge, build_index, resolve_edges
from workspace_repo_map.graph.resolvers.base import RawEdge


def test_internal_edge_merges_signals_to_high_confidence():
    exposed = {"a": {"a-pkg"}, "b": {"b-pkg"}}
    index = build_index(exposed)
    raw = {"a": [
        RawEdge("b-pkg", "manifest", "pyproject.toml", None, "b-pkg"),
        RawEdge("b_pkg", "import", "a/x.py", 3, "import b_pkg"),
    ]}
    edges, warns = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1
    e = internal[0]
    assert (e.from_repo, e.to_repo) == ("a", "b")
    assert e.confidence == "high"
    assert len(e.signals) == 2
    assert all(e.signals)  # no empty


def test_external_edge_unresolved():
    index = build_index({"a": {"a-pkg"}})
    raw = {"a": [RawEdge("requests", "manifest", "pyproject.toml", None, "requests")]}
    edges, _ = resolve_edges(raw, index)
    assert len(edges) == 1
    assert edges[0].external is True and edges[0].to_repo is None


def test_self_edge_dropped():
    index = build_index({"a": {"a-pkg"}})
    raw = {"a": [RawEdge("a-pkg", "import", "a/x.py", 1, "import a_pkg")]}
    edges, _ = resolve_edges(raw, index)
    assert edges == []


def test_ambiguous_name_is_low_confidence_with_warning():
    index = build_index({"a": {"shared"}, "b": {"shared"}, "c": set()})
    raw = {"c": [RawEdge("shared", "manifest", "pyproject.toml", None, "shared")]}
    edges, warns = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert internal and internal[0].confidence == "low"
    assert any("ambiguous" in w for w in warns)


def test_no_edge_has_empty_signals():
    index = build_index({"a": {"a-pkg"}, "b": {"b-pkg"}})
    raw = {"a": [RawEdge("b-pkg", "manifest", "pyproject.toml", None, "b-pkg")]}
    edges, _ = resolve_edges(raw, index)
    assert all(len(e.signals) >= 1 for e in edges)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_edges.py -q`
Expected: FAIL (`ModuleNotFoundError: ...graph.edges`).

- [ ] **Step 3: Implement `edges.py`**

```python
"""Resolve RawEdges into evidence-carrying repo->repo Edges."""
from __future__ import annotations

from dataclasses import dataclass

from .resolvers.base import RawEdge, normalize_name


@dataclass(frozen=True)
class Signal:
    kind: str                 # "manifest" | "import"
    evidence_file: str
    evidence_line: int | None
    raw_spec: str


@dataclass(frozen=True)
class Edge:
    from_repo: str
    to_repo: str | None
    target_name: str
    external: bool
    confidence: str           # "high" | "moderate" | "low"
    signals: tuple[Signal, ...]


def build_index(exposed: dict[str, set[str]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for repo, names in exposed.items():
        for n in names:
            index.setdefault(normalize_name(n), []).append(repo)
    return index


def _grade(signals: list[Signal], ambiguous: bool, target: str, short_len: int) -> str:
    if ambiguous or len(normalize_name(target)) <= short_len:
        return "low"
    kinds = {s.kind for s in signals}
    return "high" if {"manifest", "import"} <= kinds else "moderate"


def resolve_edges(repo_raw: dict[str, list[RawEdge]], index: dict[str, list[str]],
                  short_len: int = 2) -> tuple[list[Edge], list[str]]:
    warnings: list[str] = []
    # group RawEdges by (from_repo, resolved_target_or_external_name)
    grouped: dict[tuple[str, str | None, str], list[Signal]] = {}
    ambiguous_keys: set[tuple[str, str | None, str]] = set()
    for frm, raws in repo_raw.items():
        for r in raws:
            candidates = index.get(normalize_name(r.target_name), [])
            internal = [c for c in candidates if c != frm]
            sig = Signal(r.signal, r.evidence_file, r.evidence_line, r.raw_spec)
            if not candidates:
                key = (frm, None, normalize_name(r.target_name))  # external
            elif not internal:
                continue  # self-edge only -> drop
            else:
                to = sorted(internal)[0]
                key = (frm, to, normalize_name(r.target_name))
                if len(internal) > 1:
                    ambiguous_keys.add(key)
                    warnings.append(
                        f"ambiguous: {frm} -> {r.target_name!r} matches {sorted(internal)}")
            grouped.setdefault(key, []).append(sig)

    edges: list[Edge] = []
    for (frm, to, target), signals in grouped.items():
        external = to is None
        conf = "moderate" if external else _grade(
            signals, (frm, to, target) in ambiguous_keys, target, short_len)
        edges.append(Edge(frm, to, target, external, conf, tuple(signals)))
    edges.sort(key=lambda e: (e.from_repo, e.to_repo or "", e.target_name))
    return edges, warnings
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_edges.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workspace_repo_map/graph/edges.py tests/test_edges.py
git commit -m "feat: evidence-carrying edge resolution with confidence grading"
```

---

## Task 4: Structural roles + salience

**Files:**
- Create: `src/workspace_repo_map/graph/roles.py`
- Test: `tests/test_roles.py`

**Interfaces:**
- Consumes: `Edge` from Task 3.
- Produces:
  - `structural_salience(edges: list[Edge]) -> dict[str, dict]` -- per node `{in_degree, out_degree, hub: bool}` over internal edges only.
  - `salience_audit(salience: dict, marked: dict[str, list[str]]) -> list[dict]` -- `decorative-non-hub` / `unmarked-hub` warnings.
  - `derive_roles(repo_names: set[str], edges: list[Edge], markers: dict[str, set[str]]) -> dict[str, tuple[str, ...]]` -- repo → roles.

- [ ] **Step 1: Write the failing test**

`tests/test_roles.py`:
```python
from __future__ import annotations

from workspace_repo_map.graph.edges import Edge, Signal
from workspace_repo_map.graph.roles import (derive_roles, salience_audit,
                                            structural_salience)


def _edge(a, b):
    return Edge(a, b, "x", False, "high", (Signal("import", "f", 1, "x"),))


def test_structural_salience_hub():
    edges = [_edge("a", "c"), _edge("b", "c")]
    sal = structural_salience(edges)
    assert sal["c"]["in_degree"] == 2 and sal["c"]["hub"] is True
    assert sal["a"]["out_degree"] == 1 and sal["a"]["hub"] is False


def test_derive_roles_hub_library_entrypoint_leaf():
    edges = [_edge("app", "lib"), _edge("util", "lib")]
    markers = {"app": {"entry", "published"}, "lib": {"published"}, "leafy": set()}
    roles = derive_roles({"app", "util", "lib", "leafy"}, edges, markers)
    assert "hub" in roles["lib"] and "library" in roles["lib"]
    assert "entrypoint" in roles["app"]
    assert "leaf" in roles["leafy"]


def test_salience_audit_flags_mismatches():
    sal = {"hubnode": {"in_degree": 3, "out_degree": 0, "hub": True},
           "shiny": {"in_degree": 0, "out_degree": 1, "hub": False}}
    marked = {"shiny": ["entry"]}
    warns = salience_audit(sal, marked)
    kinds = {w["kind"] for w in warns}
    assert "decorative-non-hub" in kinds and "unmarked-hub" in kinds
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_roles.py -q`
Expected: FAIL (`ModuleNotFoundError: ...graph.roles`).

- [ ] **Step 3: Implement `roles.py`**

```python
"""Topology-derived structural roles + salience faithfulness (ported)."""
from __future__ import annotations

from .edges import Edge


def structural_salience(edges: list[Edge]) -> dict[str, dict]:
    indeg: dict[str, int] = {}
    outdeg: dict[str, int] = {}
    for e in edges:
        if e.external or e.to_repo is None:
            continue
        outdeg[e.from_repo] = outdeg.get(e.from_repo, 0) + 1
        indeg[e.to_repo] = indeg.get(e.to_repo, 0) + 1
    nodes = set(indeg) | set(outdeg)
    max_in = max(indeg.values(), default=0)
    out: dict[str, dict] = {}
    for n in sorted(nodes):
        i, o = indeg.get(n, 0), outdeg.get(n, 0)
        out[n] = {"in_degree": i, "out_degree": o, "hub": i == max_in and i >= 2}
    return out


def derive_roles(repo_names: set[str], edges: list[Edge],
                 markers: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
    sal = structural_salience(edges)
    max_out = max((s["out_degree"] for s in sal.values()), default=0)
    roles: dict[str, list[str]] = {}
    for name in sorted(repo_names):
        s = sal.get(name, {"in_degree": 0, "out_degree": 0, "hub": False})
        mk = markers.get(name, set())
        rs: list[str] = []
        if "entry" in mk:
            rs.append("entrypoint")
        if "published" in mk and s["in_degree"] >= 1 and "entry" not in mk:
            rs.append("library")
        if s["hub"]:
            rs.append("hub")
        if s["out_degree"] == max_out and s["out_degree"] >= 3:
            rs.append("orchestrator")
        if s["in_degree"] == 0 and s["out_degree"] == 0 and name in markers:
            rs.append("leaf")
        if name not in markers:
            rs.append("isolated")
        roles[name] = tuple(rs)
    return roles


def salience_audit(salience: dict[str, dict], marked: dict[str, list[str]]) -> list[dict]:
    hubs = sorted(n for n, s in salience.items() if s["hub"])
    warns: list[dict] = []
    for name, mk in sorted(marked.items()):
        if name not in hubs:
            warns.append({"kind": "decorative-non-hub", "node": name, "markers": mk,
                          "in_degree": salience.get(name, {}).get("in_degree", 0),
                          "hubs": hubs,
                          "note": "marked node is not the structural hub; a render must not let "
                                  "its marker outshine the hub(s)"})
    for h in hubs:
        if h not in marked:
            warns.append({"kind": "unmarked-hub", "node": h,
                          "in_degree": salience.get(h, {}).get("in_degree", 0),
                          "note": "structural convergence hub carries no marker; a faithful render "
                                  "should make it central"})
    return warns
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_roles.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workspace_repo_map/graph/roles.py tests/test_roles.py
git commit -m "feat: topology-derived structural roles + salience audit"
```

---

## Task 5: Graph builder

**Files:**
- Create: `src/workspace_repo_map/graph/build.py`
- Modify: `src/workspace_repo_map/graph/__init__.py` (re-export)
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `ALL_RESOLVERS`, `RawEdge`, `build_index`, `resolve_edges`, `derive_roles`.
- Produces:
  - `RepoNode(name: str, path: str, ecosystems: tuple[str, ...], exposed_names: frozenset[str], description: str, markers: frozenset[str])` (frozen).
  - `DependencyGraph(repos: tuple[RepoNode, ...], edges: tuple[Edge, ...], roles: dict[str, tuple[str, ...]], warnings: tuple[str, ...])` (frozen).
  - `detect_markers(repo_root: Path, exposed: set[str]) -> set[str]` -- `{"published"?, "entry"?}`.
  - `build_graph(repo_paths: dict[str, Path], resolvers=ALL_RESOLVERS) -> DependencyGraph`.

- [ ] **Step 1: Write the failing test**

`tests/test_build.py`:
```python
from __future__ import annotations

from pathlib import Path

from workspace_repo_map.graph.build import build_graph, detect_markers

FIX = Path(__file__).parent / "fixtures"


def test_detect_markers_entry_and_published():
    mk = detect_markers(FIX / "py_app", {"py-app"})
    assert "published" in mk and "entry" in mk


def test_build_graph_links_app_to_lib():
    graph = build_graph({"py-app": FIX / "py_app", "py-lib": FIX / "py_lib"})
    internal = [e for e in graph.edges if not e.external]
    pairs = {(e.from_repo, e.to_repo) for e in internal}
    assert ("py-app", "py-lib") in pairs
    assert "entrypoint" in graph.roles["py-app"]
    assert "hub" in graph.roles["py-lib"] or "library" in graph.roles["py-lib"]
    node = next(n for n in graph.repos if n.name == "py-app")
    assert node.ecosystems == ("python",)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_build.py -q`
Expected: FAIL (`ModuleNotFoundError: ...graph.build`).

- [ ] **Step 3: Implement `build.py`**

```python
"""Assemble repo trees + resolvers into a DependencyGraph."""
from __future__ import annotations

import configparser
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .edges import Edge, build_index, resolve_edges
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


def _description(repo_root: Path) -> str:
    for readme in ("README.md", "README.rst", "README.txt", "readme.md"):
        p = repo_root / readme
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            for block in _PARA.split(text):
                b = block.strip()
                if b and not b.startswith("#") and not b.startswith("!["):
                    return " ".join(b.split())[:300]
    pp = repo_root / "pyproject.toml"
    if pp.is_file():
        try:
            d = tomllib.loads(pp.read_text(encoding="utf-8")).get("project", {})
            if d.get("description"):
                return str(d["description"])
        except (tomllib.TOMLDecodeError, OSError):
            pass
    pj = repo_root / "package.json"
    if pj.is_file():
        try:
            d = json.loads(pj.read_text(encoding="utf-8"))
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
            data = tomllib.loads(pp.read_text(encoding="utf-8"))
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
            if json.loads(pj.read_text(encoding="utf-8")).get("bin"):
                mk.add("entry")
        except (json.JSONDecodeError, OSError):
            pass
    if any(repo_root.rglob("__main__.py")):
        mk.add("entry")
    return mk


def build_graph(repo_paths: dict[str, Path], resolvers=ALL_RESOLVERS) -> DependencyGraph:
    nodes: list[RepoNode] = []
    exposed: dict[str, set[str]] = {}
    repo_raw: dict[str, list[RawEdge]] = {}
    markers: dict[str, set[str]] = {}
    for name, root in sorted(repo_paths.items()):
        ecos: list[str] = []
        names: set[str] = set()
        raws: list[RawEdge] = []
        for r in resolvers:
            if r.matches(root):
                ecos.append(r.name)
                names |= r.exposed_names(root)
                raws += r.raw_edges(root)
        exposed[name] = names
        repo_raw[name] = raws
        mk = detect_markers(root, names)
        markers[name] = mk
        nodes.append(RepoNode(name, str(root), tuple(ecos), frozenset(names),
                              _description(root), frozenset(mk)))

    index = build_index(exposed)
    edges, warnings = resolve_edges(repo_raw, index)
    roles = derive_roles(set(repo_paths), edges, markers)
    return DependencyGraph(tuple(nodes), tuple(edges), roles, tuple(warnings))
```

- [ ] **Step 4: Re-export in `graph/__init__.py`**

```python
"""Repo-level dependency inference engine."""
from .build import DependencyGraph, RepoNode, build_graph

__all__ = ["DependencyGraph", "RepoNode", "build_graph"]
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_build.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/workspace_repo_map/graph/build.py src/workspace_repo_map/graph/__init__.py tests/test_build.py
git commit -m "feat: graph builder assembling resolvers into a DependencyGraph"
```

---

## Task 6: Context pack renderer

**Files:**
- Create: `src/workspace_repo_map/context/__init__.py`
- Create: `src/workspace_repo_map/context/pack.py`
- Test: `tests/test_pack.py`

**Interfaces:**
- Consumes: `DependencyGraph`, `RepoNode`, `Edge`, `structural_salience`, `salience_audit`.
- Produces:
  - `render_text(graph: DependencyGraph, title: str) -> str`.
  - `to_json(graph: DependencyGraph) -> dict`.
  - `closure(edges, focus: str) -> set[str]` (bidirectional, cycle-safe).
  - `focus_subgraph(graph: DependencyGraph, keep: set[str]) -> DependencyGraph`.

- [ ] **Step 1: Write the failing test**

`tests/test_pack.py`:
```python
from __future__ import annotations

import inspect
from pathlib import Path

from workspace_repo_map.context import pack
from workspace_repo_map.context.pack import (closure, focus_subgraph, render_text,
                                             to_json)
from workspace_repo_map.graph.build import build_graph

FIX = Path(__file__).parent / "fixtures"


def _graph():
    return build_graph({"py-app": FIX / "py_app", "py-lib": FIX / "py_lib"})


def test_render_text_has_three_sections_and_evidence():
    text = render_text(_graph(), "test")
    assert "## Roles" in text and "## Relations" in text and "## Inventory" in text
    assert "py-app -> py-lib" in text


def test_to_json_carries_salience_and_audit():
    data = to_json(_graph())
    assert "salience" in data and "salience_audit" in data
    assert "relations" in data and "roles" in data


def test_closure_is_bidirectional_and_cycle_safe():
    g = _graph()
    keep = closure(list(g.edges), "py-lib")
    assert "py-app" in keep and "py-lib" in keep  # reached upstream
    sub = focus_subgraph(g, keep)
    assert {n.name for n in sub.repos} == keep


def test_no_editorializing_no_banned_phrases_in_source():
    src = inspect.getsource(pack)
    banned = ["keystone", "the heart of", "is the most important", "clearly the",
              "obviously", "the best"]
    assert not [b for b in banned if b in src.lower()]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_pack.py -q`
Expected: FAIL (`ModuleNotFoundError: ...context.pack`).

- [ ] **Step 3: Implement `context/__init__.py` and `pack.py`**

`src/workspace_repo_map/context/__init__.py`:
```python
"""Synthesis context-pack renderer."""
```

`src/workspace_repo_map/context/pack.py`:
```python
"""Render a DependencyGraph as the synthesis context pack (relations+roles+prose).

No editorializing: every line traces to a data field or an evidence record.
"""
from __future__ import annotations

from ..graph.build import DependencyGraph, RepoNode
from ..graph.edges import Edge
from ..graph.roles import salience_audit, structural_salience


def _marker_list(node: RepoNode) -> list[str]:
    out = []
    if "entry" in node.markers:
        out.append("entry")
    if "published" in node.markers:
        out.append("published")
    return out


def render_text(graph: DependencyGraph, title: str) -> str:
    L = [f"# Context pack: {title}", ""]
    L.append("## Roles (project: roles -- in/out degree)")
    sal = structural_salience(list(graph.edges))
    for node in sorted(graph.repos, key=lambda n: n.name):
        rs = ", ".join(graph.roles.get(node.name, ())) or "(none)"
        s = sal.get(node.name, {"in_degree": 0, "out_degree": 0})
        L.append(f"- {node.name}: {rs} -- in={s['in_degree']} out={s['out_degree']}")
    L.append("")
    L.append("## Relations (A -> B: signals [confidence])")
    for e in graph.edges:
        if e.external:
            continue
        kinds = "+".join(sorted({s.kind for s in e.signals}))
        L.append(f"- {e.from_repo} -> {e.to_repo}: {kinds} [{e.confidence}]")
    L.append("")
    L.append("## External dependencies (A -> name)")
    for e in graph.edges:
        if e.external:
            L.append(f"- {e.from_repo} -> {e.target_name}")
    L.append("")
    L.append("## Inventory (all projects -- extracted description)")
    for node in sorted(graph.repos, key=lambda n: n.name):
        eco = "/".join(node.ecosystems) or "none"
        L.append(f"- {node.name} [{eco}]: {node.description}")
    L.append("")
    if graph.warnings:
        L.append(f"## Warnings ({len(graph.warnings)})")
        for w in graph.warnings:
            L.append(f"- {w}")
    return "\n".join(L)


def to_json(graph: DependencyGraph) -> dict:
    sal = structural_salience(list(graph.edges))
    marked = {n.name: _marker_list(n) for n in graph.repos if _marker_list(n)}
    relations = [{
        "from": e.from_repo, "to": e.to_repo, "target_name": e.target_name,
        "external": e.external, "confidence": e.confidence,
        "signals": [{"kind": s.kind, "file": s.evidence_file, "line": s.evidence_line,
                     "raw": s.raw_spec} for s in e.signals],
    } for e in graph.edges]
    return {
        "roles": {n.name: list(graph.roles.get(n.name, ())) for n in graph.repos},
        "relations": relations,
        "salience": sal,
        "salience_audit": salience_audit(sal, marked),
        "repos": [{"name": n.name, "ecosystems": list(n.ecosystems),
                   "description": n.description, "markers": sorted(n.markers)}
                  for n in graph.repos],
        "warnings": list(graph.warnings),
    }


def closure(edges: list[Edge], focus: str) -> set[str]:
    adj: dict[str, set[str]] = {}
    for e in edges:
        if e.external or e.to_repo is None:
            continue
        adj.setdefault(e.from_repo, set()).add(e.to_repo)
        adj.setdefault(e.to_repo, set()).add(e.from_repo)
    seen = {focus}
    stack = [focus]
    while stack:
        n = stack.pop()
        for m in adj.get(n, ()):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


def focus_subgraph(graph: DependencyGraph, keep: set[str]) -> DependencyGraph:
    repos = tuple(n for n in graph.repos if n.name in keep)
    edges = tuple(e for e in graph.edges
                  if e.from_repo in keep and (e.external or e.to_repo in keep))
    roles = {k: v for k, v in graph.roles.items() if k in keep}
    return DependencyGraph(repos, edges, roles, graph.warnings)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_pack.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/workspace_repo_map/context tests/test_pack.py
git commit -m "feat: context-pack renderer (relations+roles+prose, no editorializing)"
```

---

## Task 7: CLI subcommands + backward compatibility

**Files:**
- Modify: `src/workspace_repo_map/cli.py`
- Test: `tests/test_cli_subcommands.py`

**Interfaces:**
- Consumes: `build_graph`, `render_text`, `to_json`, `closure`, `focus_subgraph`, `discover_repos`/`build_map` (existing sensor).
- Produces: `main(argv)` dispatching `map` (default), `graph`, `context`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli_subcommands.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from workspace_repo_map.cli import main

FIX = Path(__file__).parent / "fixtures"


def test_backward_compat_bare_invocation_writes_map(tmp_path, capsys):
    rc = main(["--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "repositories" in data  # the existing map shape


def test_graph_subcommand_json(capsys):
    rc = main(["graph", "--root", str(FIX), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "relations" in data and "roles" in data


def test_context_focus_unknown_returns_2(capsys):
    rc = main(["context", "--root", str(FIX), "--focus", "nope-xyz"])
    assert rc == 2


def test_context_focus_known(capsys):
    rc = main(["context", "--root", str(FIX), "--focus", "py-lib"])
    out = capsys.readouterr().out
    assert rc == 0 and "## Relations" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_cli_subcommands.py -q`
Expected: FAIL (subcommands unrecognized / `graph` treated as `--root` error).

- [ ] **Step 3: Rewrite `cli.py`**

```python
"""Command-line entry point: map (default) + graph + context subcommands."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from . import __version__
from .config import load_config
from .context.pack import closure, focus_subgraph, render_text, to_json
from .graph.build import build_graph
from .scan import build_map, discover_repos, write_map

_SUBCOMMANDS = {"map", "graph", "context"}


# discover_repos(root, config) -> list[Path] of repo roots (verified against scan.py)


def _add_map_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--jobs", type=int, default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-repo-map",
        description="Repository inventory maps + dependency graph + context packs.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    _add_map_args(sub.add_parser("map", help="Write the repository inventory map (default)."))

    g = sub.add_parser("graph", help="Derive the repo-level dependency graph.")
    g.add_argument("--root", type=Path, default=Path.cwd())
    g.add_argument("--json", action="store_true")

    c = sub.add_parser("context", help="Render the synthesis context pack.")
    c.add_argument("--root", type=Path, default=Path.cwd())
    c.add_argument("--json", action="store_true")
    c.add_argument("--focus", default=None)
    c.add_argument("--audit", action="store_true")
    return parser


def _repo_paths(root: Path) -> dict[str, Path]:
    # discover_repos requires a Config; use neutral defaults for graph/context.
    config = load_config(None, root)
    return {p.name: p for p in discover_repos(root, config)}


def _cmd_map(args) -> int:
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    config = load_config(args.config, root)
    if args.jobs is not None:
        if args.jobs < 1:
            raise SystemExit("--jobs must be a positive integer")
        config = replace(config, jobs=args.jobs)
    if args.json:
        print(json.dumps(build_map(root, config, __version__).to_json(), indent=2))
    else:
        output = args.output.resolve() if args.output else root / "WORKSPACE-REPO-MAP.json"
        data = write_map(root, config, __version__, output)
        print(f"wrote {output}")
        print(f"repos={data.repo_count} dirty={data.dirty_count}")
    return 0


def _cmd_graph(args) -> int:
    graph = build_graph(_repo_paths(args.root.resolve()))
    if args.json:
        print(json.dumps(to_json(graph), indent=2))
    else:
        print(render_text(graph, "dependency graph"))
    return 0


def _cmd_context(args) -> int:
    graph = build_graph(_repo_paths(args.root.resolve()))
    names = {n.name for n in graph.repos}
    if args.audit:
        data = to_json(graph)
        print(f"salience-faithfulness warnings: {len(data['salience_audit'])}")
        for w in data["salience_audit"]:
            print(f"  [{w['kind']}] {w['node']} (in={w['in_degree']}) -- {w['note']}")
        return 0
    if args.focus:
        if args.focus not in names:
            near = [n for n in names if args.focus.lower() in n.lower()]
            print(f"unknown project: {args.focus!r}"
                  + (f" -- did you mean: {', '.join(sorted(near))}?" if near else ""))
            return 2
        graph = focus_subgraph(graph, closure(list(graph.edges), args.focus))
        title = f"focus={args.focus}"
    else:
        title = "workstation context"
    print(json.dumps(to_json(graph), indent=2) if args.json else render_text(graph, title))
    return 0


def main(argv: list[str] | None = None) -> int:
    import sys
    raw = list(sys.argv[1:] if argv is None else argv)
    # backward compat: no subcommand -> implicit `map`
    if not raw or (raw[0].startswith("-") and raw[0] != "--version") or raw[0] not in _SUBCOMMANDS:
        if raw and raw[0] == "--version":
            build_parser().parse_args(raw)
        raw = ["map", *raw] if (not raw or raw[0] not in _SUBCOMMANDS) else raw
    args = build_parser().parse_args(raw)
    if args.cmd == "graph":
        return _cmd_graph(args)
    if args.cmd == "context":
        return _cmd_context(args)
    return _cmd_map(args)
```

Note: confirm `discover_repos` returns an iterable of repo root `Path`s. If its signature differs, adapt `_repo_paths` to it (it is exported from `scan` per `__init__.py`).

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_cli_subcommands.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full suite (no regressions in the sensor)**

Run: `python -m pytest -q`
Expected: PASS (all existing sensor tests + the new modules).

- [ ] **Step 6: Commit**

```bash
git add src/workspace_repo_map/cli.py tests/test_cli_subcommands.py
git commit -m "feat: map/graph/context subcommands with backward-compatible default"
```

---

## Task 8: Dogfood acceptance harness (opt-in)

**Files:**
- Create: `scripts/dogfood_recovery.py`
- Test: none (this IS the acceptance harness; it is run manually, not in the unit slice).

**Interfaces:**
- Consumes: `build_graph`. Reads the author's corpus as read-only test data.

- [ ] **Step 1: Implement the recovery harness**

`scripts/dogfood_recovery.py`:
```python
"""Dogfood: run the graph engine over a corpus and report edge recovery.

Compares the engine's inferred internal edges against a hand-authored edge set
(if available) and prints recall + false-positive counts. Read-only; no writes.

Usage:
    python scripts/dogfood_recovery.py --root C:/dev [--truth path/to/edges.json]

--truth is an optional JSON list of {"from": repo, "to": repo} hand-authored edges.
Without it, the harness just prints the inferred graph summary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workspace_repo_map.config import load_config
from workspace_repo_map.graph.build import build_graph
from workspace_repo_map.scan import discover_repos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--truth", type=Path, default=None)
    args = ap.parse_args(argv)

    root = args.root.resolve()
    paths = {p.name: p for p in discover_repos(root, load_config(None, root))}
    graph = build_graph(paths)
    inferred = {(e.from_repo, e.to_repo) for e in graph.edges if not e.external}
    print(f"repos={len(graph.repos)} internal_edges={len(inferred)} "
          f"external_edges={sum(1 for e in graph.edges if e.external)} "
          f"warnings={len(graph.warnings)}")

    if args.truth and args.truth.is_file():
        truth = {(d["from"], d["to"]) for d in json.loads(args.truth.read_text("utf-8"))}
        recovered = inferred & truth
        missed = truth - inferred
        extra = inferred - truth
        recall = len(recovered) / len(truth) if truth else 0.0
        print(f"truth_edges={len(truth)} recovered={len(recovered)} "
              f"recall={recall:.0%} missed={len(missed)} new_inferred={len(extra)}")
        if missed:
            print("missed (hand-authored, not inferred):")
            for a, b in sorted(missed):
                print(f"  {a} -> {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the harness over the corpus (manual acceptance)**

Run: `python scripts/dogfood_recovery.py --root C:/dev`
Expected: prints a summary line (repos / internal_edges / external_edges / warnings). Record the numbers. This is the baseline; recall against a truth file is reported when one is supplied.

- [ ] **Step 3: Commit**

```bash
git add scripts/dogfood_recovery.py
git commit -m "feat: dogfood recovery harness for corpus acceptance"
```

---

## Self-Review

**Spec coverage:**
- Resolver seam → Task 1 (base.py). ✓
- Python resolver → Task 1. ✓
- JS/TS resolver → Task 2. ✓
- Pluggable registry → Task 2 (`ALL_RESOLVERS`). ✓
- Edge + evidence model + confidence + no-empty-signals invariant → Task 3. ✓
- External-vs-internal + ambiguity + self-edge → Task 3. ✓
- Structural roles (6 archetypes) → Task 4. ✓
- Salience + audit (ported) → Task 4. ✓
- Graph builder + markers + prose extraction → Task 5. ✓
- Context pack (3 sections + external + warnings), JSON sidecar → Task 6. ✓
- No-editorializing structural test → Task 6. ✓
- `--focus` bidirectional closure → Task 6 + Task 7. ✓
- CLI subcommands + backward compat → Task 7. ✓
- Fail-closed error handling → present in every resolver/build try/except. ✓
- Dogfood acceptance (recovery metric) → Task 8. ✓
- Zero new runtime deps → Global Constraints; only stdlib imports used. ✓

**Placeholder scan:** No TBD/TODO; the one `Note:` in Task 7 is a verification instruction (confirm `discover_repos` signature), not a placeholder -- it names the exact symbol and fallback.

**Type consistency:** `RawEdge`, `Signal`, `Edge`, `RepoNode`, `DependencyGraph` field names are used identically across Tasks 1, 3, 5, 6, 7. `structural_salience(edges)`, `salience_audit(salience, marked)`, `derive_roles(repo_names, edges, markers)`, `build_graph(repo_paths)`, `closure(edges, focus)`, `focus_subgraph(graph, keep)` signatures match between definition and call sites.

**Verified against source:** `discover_repos(root: Path, config: Config) -> list[Path]` returns repo-root paths (checked in `scan.py`); the plan passes a neutral `load_config(None, root)` at both call sites (`cli._repo_paths` and `scripts/dogfood_recovery.py`). One known v1 limitation: repos are keyed by basename, so two repos sharing a basename collide (last wins) -- acceptable at repo-level granularity for v1; revisit if the corpus dogfood surfaces real collisions.
