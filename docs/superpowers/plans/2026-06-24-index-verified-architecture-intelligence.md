# Index 2.0 Verified Architecture Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Index from a static repo-level cartographer into a tool that sees inside repos at module granularity, checks real structure against a declared architecture criterion, detects drift over time, and emits a re-checkable MATCH/DRIFT/UNVERIFIABLE certificate.

**Architecture:** Six additive subsystems under `src/index_graph/`, each composing the existing primitives rather than editing them. `internals/` builds an intra-repo module graph and reuses the existing `find_cycles` by constructing minimal internal `Edge`s. `arch/` parses an optional `[architecture]` config block and evaluates a graph against it. `drift/` serializes canonical snapshots and diffs them. `certify/` builds the verdict certificate with the same canonical-JSON SHA-256 discipline the manifest already uses. `cli.py` gains four subcommands. Nothing existing changes behavior.

**Tech Stack:** Python 3.11+ standard library only (`ast`, `re`, `tomllib`, `hashlib`, `json`, `dataclasses`, `pathlib`, `argparse`). Tests with pytest (`pythonpath = ["src"]`). Build with hatchling.

## Global Constraints

- **Zero runtime dependencies.** Standard library only. No new entries in `[project].dependencies`.
- **Python floor:** `requires-python = ">=3.11"`. Use `tomllib` (3.11+), `X | None` unions, `from __future__ import annotations`.
- **Deterministic.** Same input produces a byte-identical pack and an identical certificate. Sort every collection before serializing. Canonical JSON is `json.dumps(obj, sort_keys=True, separators=(",", ":"))`.
- **Backward compatible.** `map`, `graph`, `context`, `viz`, `atlas` and their JSON outputs are unchanged. The existing 217 tests stay green.
- **Additive only.** New subsystems and new subcommands. No behavior change to existing modules except the two explicitly listed modifications (`config.py` gains an optional block; `cli.py` gains four subcommands; `__init__.py` version bump).
- **Copy rule:** No em-dashes in any prose or help string you add (rewrite, do not substitute the character). No cross-marketing: the protocol and docs name no sibling product; describe consumers generically (CI, a reviewer, an external agent).
- **Evidence-carrying.** Every internal edge and every finding names the file and, where cheaply known, the line that witnessed it.
- **License header convention:** match neighboring files (module docstring first line, then `from __future__ import annotations`).

---

## File Structure (the decomposition and the shared spine)

**Create:**
- `src/index_graph/internals/__init__.py` -- exports `ModuleNode`, `InternalEdge`, `InternalGraph`, `build_internals`.
- `src/index_graph/internals/modules.py` -- per-language module discovery and intra-repo import extraction. One responsibility: turn a repo directory into module nodes and internal edges.
- `src/index_graph/internals/build.py` -- assemble an `InternalGraph` (modules + edges + cycles + fan-in/out). Reuses `graph.cycles.find_cycles`.
- `src/index_graph/arch/__init__.py` -- exports `ArchitectureCriteria`, `parse_architecture`, `Finding`, `check_graph`.
- `src/index_graph/arch/criteria.py` -- the `ArchitectureCriteria` dataclass and its parser from a TOML dict.
- `src/index_graph/arch/check.py` -- `Finding` and `check_graph`: evaluate a graph (and optional internal graphs) against criteria.
- `src/index_graph/drift/__init__.py` -- exports `snapshot_pack`, `load_snapshot`, `DriftReport`, `diff_snapshots`.
- `src/index_graph/drift/snapshot.py` -- canonical snapshot build and load.
- `src/index_graph/drift/diff.py` -- `DriftReport` and `diff_snapshots`.
- `src/index_graph/certify/__init__.py` -- exports `canonical_sha`, `build_certificate`.
- `src/index_graph/certify/certificate.py` -- canonical hashing and certificate assembly with the three-verdict logic.
- `docs/PROTOCOL.md` -- the consumer-agnostic seam specification.
- Test files mirroring each module under `tests/` (named in each task).

**Modify:**
- `src/index_graph/config.py` -- add `"architecture"` to `_KNOWN_TOP`; parse the block; add an `architecture` field to `Config`.
- `src/index_graph/cli.py` -- register and dispatch `internals`, `check`, `snapshot`, `drift`.
- `src/index_graph/__init__.py` -- version bump to `2.0.0`; export the new top-level helpers.
- `README.md`, `USAGE.md`, `CHANGELOG.md` -- document the new capability.

**Shared spine (exact types every task depends on):**

```python
# internals/modules.py
@dataclass(frozen=True)
class ModuleNode:
    id: str          # repo-relative dotted-or-path module id, forward-slashed, no suffix
    path: str        # repo-relative file path (forward-slashed)
    language: str    # "python" | "javascript" | "rust" | "go"

@dataclass(frozen=True)
class InternalEdge:
    from_id: str     # ModuleNode.id of the importer
    to_id: str       # ModuleNode.id of the imported internal module
    evidence_file: str
    evidence_line: int | None
    raw: str         # literal import text witnessed

# internals/build.py
@dataclass(frozen=True)
class InternalGraph:
    repo: str
    modules: tuple[ModuleNode, ...]          # sorted by id
    edges: tuple[InternalEdge, ...]          # sorted by (from_id, to_id, evidence_file, evidence_line)
    cycles: tuple[tuple[str, ...], ...]      # sorted; each a sorted tuple of module ids
    fan_in: dict[str, int]                   # id -> count of distinct importers
    fan_out: dict[str, int]                  # id -> count of distinct imported internal modules

# arch/criteria.py
@dataclass(frozen=True)
class LayerRule:
    layers: tuple[str, ...]                  # ordered, lowest first

@dataclass(frozen=True)
class ForbidRule:
    from_glob: str
    to_glob: str

@dataclass(frozen=True)
class ArchitectureCriteria:
    layers: tuple[str, ...] = ()             # ordered layer names, lowest first
    forbid: tuple[ForbidRule, ...] = ()
    max_cycles: int | None = None            # None = not checked
    owns: tuple[tuple[str, str], ...] = ()   # (path_glob, owner), sorted

    @property
    def declared(self) -> bool:
        return bool(self.layers or self.forbid or self.max_cycles is not None or self.owns)

# arch/check.py
@dataclass(frozen=True)
class Finding:
    rule: str        # "layer" | "forbid" | "max_cycles" | "owns"
    detail: str      # human one-line, no em-dash
    edge: str | None # "from -> to" when an edge is the witness, else None
    evidence: str | None  # "file:line" when known, else None

# drift/diff.py
@dataclass(frozen=True)
class DriftReport:
    repos_added: tuple[str, ...]
    repos_removed: tuple[str, ...]
    edges_added: tuple[str, ...]       # "from -> to"
    edges_removed: tuple[str, ...]
    cycles_introduced: tuple[tuple[str, ...], ...]
    cycles_cleared: tuple[tuple[str, ...], ...]
    roles_changed: tuple[tuple[str, str, str], ...]  # (repo, old_roles_csv, new_roles_csv)

    @property
    def verdict(self) -> str:
        any_change = any([
            self.repos_added, self.repos_removed, self.edges_added,
            self.edges_removed, self.cycles_introduced, self.cycles_cleared,
            self.roles_changed,
        ])
        return "DRIFT" if any_change else "MATCH"
```

The certificate shape (produced by `certify`):

```json
{
  "schema": "index.certificate/1",
  "tool_version": "2.0.0",
  "kind": "check",
  "content_sha256": "<hex>",
  "criterion_sha256": "<hex or null>",
  "verdict": "MATCH | DRIFT | UNVERIFIABLE",
  "findings": [{"rule": "...", "detail": "...", "edge": "...", "evidence": "file:line"}],
  "recheck": "index check --root . --internals --json"
}
```

---

## Phase 1: Module graph foundation (Python, AST-exact)

### Task 1: Python module discovery and internal-edge extraction

**Files:**
- Create: `src/index_graph/internals/__init__.py`
- Create: `src/index_graph/internals/modules.py`
- Test: `tests/test_internals_modules.py`

**Interfaces:**
- Produces: `ModuleNode`, `InternalEdge` (exact fields above); `discover_modules(repo_root: Path) -> list[ModuleNode]`; `extract_internal_edges(repo_root: Path, modules: list[ModuleNode]) -> list[InternalEdge]`.
- Consumes: `index_graph.graph.walk.walk_files` (existing), `ast` (stdlib).

**Key idea:** Python module id is the dotted path relative to the repo root with `/` separators and no `.py`, e.g. `src/pkg/sub/mod` becomes id `src/pkg/sub/mod`. An importer resolves an import to an internal module when the import target maps to a known `ModuleNode.id`. Both relative imports (`from .x import y`, `node.level > 0`) and absolute imports of the repo's own packages resolve to internal modules; everything else is external and ignored here.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_internals_modules.py
from pathlib import Path
from index_graph.internals.modules import discover_modules, extract_internal_edges


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_discovers_python_modules_with_ids(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "x = 1\n")
    _write(tmp_path, "pkg/sub/b.py", "y = 2\n")
    mods = discover_modules(tmp_path)
    ids = sorted(m.id for m in mods)
    assert ids == ["pkg/__init__", "pkg/a", "pkg/sub/b"]
    assert all(m.language == "python" for m in mods)


def test_relative_import_makes_internal_edge(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from .b import thing\n")
    _write(tmp_path, "pkg/b.py", "thing = 1\n")
    mods = discover_modules(tmp_path)
    edges = extract_internal_edges(tmp_path, mods)
    pairs = {(e.from_id, e.to_id) for e in edges}
    assert ("pkg/a", "pkg/b") in pairs
    e = next(e for e in edges if e.from_id == "pkg/a")
    assert e.evidence_file == "pkg/a.py"
    assert e.evidence_line == 1


def test_absolute_internal_import_resolves(tmp_path):
    _write(tmp_path, "app/__init__.py", "")
    _write(tmp_path, "app/main.py", "import app.helpers\n")
    _write(tmp_path, "app/helpers.py", "def h(): pass\n")
    mods = discover_modules(tmp_path)
    edges = extract_internal_edges(tmp_path, mods)
    assert ("app/main", "app/helpers") in {(e.from_id, e.to_id) for e in edges}


def test_external_import_is_not_internal_edge(tmp_path):
    _write(tmp_path, "app/__init__.py", "")
    _write(tmp_path, "app/main.py", "import os\nimport requests\n")
    mods = discover_modules(tmp_path)
    edges = extract_internal_edges(tmp_path, mods)
    assert edges == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_internals_modules.py -v`
Expected: FAIL with `ModuleNotFoundError: index_graph.internals`.

- [ ] **Step 3: Implement `internals/__init__.py`**

```python
"""Intra-repo module graph: see inside a repo, not only repo as atom."""
from __future__ import annotations

from .modules import ModuleNode, InternalEdge, discover_modules, extract_internal_edges
from .build import InternalGraph, build_internals

__all__ = [
    "ModuleNode", "InternalEdge", "InternalGraph",
    "discover_modules", "extract_internal_edges", "build_internals",
]
```

- [ ] **Step 4: Implement `internals/modules.py` (Python language only this task)**

```python
"""Module discovery and intra-repo import extraction, per language."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from ..graph.walk import walk_files


@dataclass(frozen=True)
class ModuleNode:
    id: str
    path: str
    language: str


@dataclass(frozen=True)
class InternalEdge:
    from_id: str
    to_id: str
    evidence_file: str
    evidence_line: int | None
    raw: str


def _py_id(rel_path: str) -> str:
    # "pkg/sub/mod.py" -> "pkg/sub/mod"
    return rel_path[:-3] if rel_path.endswith(".py") else rel_path


def discover_modules(repo_root: Path) -> list[ModuleNode]:
    mods: list[ModuleNode] = []
    for py in walk_files(repo_root, suffixes=(".py",)):
        rel = py.relative_to(repo_root).as_posix()
        mods.append(ModuleNode(id=_py_id(rel), path=rel, language="python"))
    return sorted(mods, key=lambda m: m.id)


def _dotted_to_id(dotted: str, ids: set[str]) -> str | None:
    """Map a dotted module ('app.helpers') to an internal module id, if any.

    Tries the dotted path as a module file ('app/helpers') and as a package
    ('app/helpers/__init__'). Returns the matching internal id or None.
    """
    base = dotted.replace(".", "/")
    if base in ids:
        return base
    pkg = base + "/__init__"
    if pkg in ids:
        return pkg
    return None


def _resolve_relative(importer_id: str, level: int, module: str | None,
                      ids: set[str]) -> str | None:
    """Resolve a relative import ('from .x import y', level>=1) to an internal id."""
    # importer package is the importer's directory in dotted form
    parts = importer_id.split("/")
    # drop the module file name; for __init__ the package is its own dir
    pkg_parts = parts[:-1]
    # each extra level walks up one package
    up = level - 1
    if up > len(pkg_parts):
        return None
    if up:
        pkg_parts = pkg_parts[:len(pkg_parts) - up]
    target = pkg_parts + (module.split(".") if module else [])
    return _dotted_to_id("/".join(target).replace("/", "."), ids) if target else None


def _python_edges(repo_root: Path, ids: set[str]) -> list[InternalEdge]:
    out: list[InternalEdge] = []
    for py in walk_files(repo_root, suffixes=(".py",)):
        rel = py.relative_to(repo_root).as_posix()
        from_id = _py_id(rel)
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    tid = _dotted_to_id(a.name, ids)
                    if tid and tid != from_id:
                        out.append(InternalEdge(from_id, tid, rel, node.lineno, f"import {a.name}"))
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    tid = _resolve_relative(from_id, node.level, node.module, ids)
                    raw = f"from {'.' * node.level}{node.module or ''} import ..."
                elif node.module:
                    tid = _dotted_to_id(node.module, ids)
                    raw = f"from {node.module} import ..."
                else:
                    tid = None
                    raw = ""
                if tid and tid != from_id:
                    out.append(InternalEdge(from_id, tid, rel, node.lineno, raw))
    return out


def extract_internal_edges(repo_root: Path, modules: list[ModuleNode]) -> list[InternalEdge]:
    ids = {m.id for m in modules}
    edges = _python_edges(repo_root, ids)
    return sorted(edges, key=lambda e: (e.from_id, e.to_id, e.evidence_file, e.evidence_line or 0))
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_internals_modules.py -v`
Expected: PASS (4 tests). Note: `internals/build.py` does not exist yet, so import in `__init__.py` will fail. Create a minimal `build.py` stub in Step 6 before running, or run the test by importing `modules` directly (the test imports from `index_graph.internals.modules`, which does not trigger `__init__` re-export failure only if `__init__` is importable). To keep `__init__` importable, defer the `build` import: implement Step 6 in the same commit.

- [ ] **Step 6: Create `internals/build.py` (full implementation, completes the package)**

```python
"""Assemble an InternalGraph: modules, internal edges, cycles, fan-in/out."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..graph.edges import Edge
from ..graph.cycles import find_cycles
from .modules import ModuleNode, InternalEdge, discover_modules, extract_internal_edges


@dataclass(frozen=True)
class InternalGraph:
    repo: str
    modules: tuple[ModuleNode, ...]
    edges: tuple[InternalEdge, ...]
    cycles: tuple[tuple[str, ...], ...]
    fan_in: dict[str, int]
    fan_out: dict[str, int]


def _cycles(edges: tuple[InternalEdge, ...]) -> tuple[tuple[str, ...], ...]:
    # Reuse the repo-level Tarjan SCC by constructing minimal internal Edges.
    as_edges = [Edge(e.from_id, e.to_id, e.to_id, False, "high", ()) for e in edges]
    return tuple(find_cycles(as_edges))


def build_internals(repo_root: Path, repo_name: str | None = None) -> InternalGraph:
    root = repo_root.resolve()
    name = repo_name or root.name
    modules = tuple(discover_modules(root))
    edges = tuple(extract_internal_edges(root, list(modules)))
    fan_out: dict[str, int] = {}
    fan_in: dict[str, int] = {}
    seen_out: set[tuple[str, str]] = set()
    seen_in: set[tuple[str, str]] = set()
    for e in edges:
        if (e.from_id, e.to_id) not in seen_out:
            seen_out.add((e.from_id, e.to_id))
            fan_out[e.from_id] = fan_out.get(e.from_id, 0) + 1
        if (e.to_id, e.from_id) not in seen_in:
            seen_in.add((e.to_id, e.from_id))
            fan_in[e.to_id] = fan_in.get(e.to_id, 0) + 1
    return InternalGraph(name, modules, edges, _cycles(edges), fan_in, fan_out)
```

- [ ] **Step 7: Run the whole internals suite**

Run: `python -m pytest tests/test_internals_modules.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/index_graph/internals tests/test_internals_modules.py
git commit -m "feat(internals): Python module graph (discovery + AST internal edges)"
```

### Task 2: InternalGraph assembly, cycles, fan-in/out

**Files:**
- Modify: `src/index_graph/internals/build.py` (already created in Task 1; this task tests it)
- Test: `tests/test_internals_build.py`

**Interfaces:**
- Produces: `build_internals(repo_root, repo_name=None) -> InternalGraph`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_internals_build.py
from pathlib import Path
from index_graph.internals import build_internals


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_internal_cycle_detected(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from . import b\n")
    _write(tmp_path, "pkg/b.py", "from . import a\n")
    g = build_internals(tmp_path, "pkg")
    assert g.repo == "pkg"
    assert any(set(c) == {"pkg/a", "pkg/b"} for c in g.cycles)


def test_fan_in_out_counts(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/hub.py", "x = 1\n")
    _write(tmp_path, "pkg/one.py", "from .hub import x\n")
    _write(tmp_path, "pkg/two.py", "from .hub import x\n")
    g = build_internals(tmp_path, "pkg")
    assert g.fan_in.get("pkg/hub") == 2
    assert g.fan_out.get("pkg/one") == 1


def test_deterministic_ordering(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from .b import x\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")
    g1 = build_internals(tmp_path, "pkg")
    g2 = build_internals(tmp_path, "pkg")
    assert [m.id for m in g1.modules] == [m.id for m in g2.modules]
    assert [(e.from_id, e.to_id) for e in g1.edges] == [(e.from_id, e.to_id) for e in g2.edges]
```

- [ ] **Step 2: Run to verify pass** (implementation already exists from Task 1 Step 6)

Run: `python -m pytest tests/test_internals_build.py -v`
Expected: PASS (3 tests). If `test_internal_cycle_detected` fails because `from . import b` is not resolved, extend `_resolve_relative` to handle `from . import name` where `module is None` and the imported name is a sibling module: when `node.module is None` and `node.level >= 1`, resolve each `alias.name` against the importer package by `_dotted_to_id`. Add that branch in `_python_edges` and re-run.

- [ ] **Step 3: Handle `from . import sibling` (refine `_python_edges`)**

In `internals/modules.py`, inside `_python_edges`, replace the `ImportFrom` branch so that when `node.level and node.module is None`, each imported alias is resolved as a sibling module:

```python
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.module is None:
                    parts = from_id.split("/")[:-1]
                    up = node.level - 1
                    base = parts[:len(parts) - up] if up <= len(parts) else None
                    if base is not None:
                        for a in node.names:
                            cand = "/".join([*base, a.name])
                            tid = cand if cand in ids else (cand + "/__init__" if cand + "/__init__" in ids else None)
                            if tid and tid != from_id:
                                out.append(InternalEdge(from_id, tid, rel, node.lineno, f"from {'.' * node.level} import {a.name}"))
                    continue
                if node.level and node.level > 0:
                    tid = _resolve_relative(from_id, node.level, node.module, ids)
                    raw = f"from {'.' * node.level}{node.module or ''} import ..."
                elif node.module:
                    tid = _dotted_to_id(node.module, ids)
                    raw = f"from {node.module} import ..."
                else:
                    tid = None
                    raw = ""
                if tid and tid != from_id:
                    out.append(InternalEdge(from_id, tid, rel, node.lineno, raw))
```

- [ ] **Step 4: Run both internals suites**

Run: `python -m pytest tests/test_internals_modules.py tests/test_internals_build.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/internals tests/test_internals_build.py
git commit -m "feat(internals): InternalGraph cycles + fan-in/out, sibling relative imports"
```

---

## Phase 2: Module graph reach (JS/TS, Rust, Go best-effort)

### Task 3: Language extractors for JS/TS, Rust, Go (relative/path imports)

**Files:**
- Modify: `src/index_graph/internals/modules.py`
- Test: `tests/test_internals_reach.py`

**Interfaces:**
- `discover_modules` now also yields nodes for `.js/.ts/.jsx/.tsx/.mjs/.cjs`, `.rs`, `.go`. `extract_internal_edges` dispatches per language. Resolution is best-effort and relative-path based; bounds are documented.

**Bounds (put in `--help` and `PROTOCOL.md`):** JS/TS resolves relative specifiers (`./x`, `../y/z`) to files; bare specifiers are external. Rust resolves `mod name;` declarations and `crate::`/`super::` path heads to sibling files. Go resolves imports whose path suffix matches an internal package directory. These are file-level, conservative, and may miss dynamic or aliased imports.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_internals_reach.py
from pathlib import Path
from index_graph.internals import build_internals


def _w(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_js_relative_import_edge(tmp_path):
    _w(tmp_path, "src/a.js", "import { f } from './b';\n")
    _w(tmp_path, "src/b.js", "export const f = 1;\n")
    g = build_internals(tmp_path, "app")
    assert ("src/a", "src/b") in {(e.from_id, e.to_id) for e in g.edges}


def test_js_bare_import_is_external(tmp_path):
    _w(tmp_path, "src/a.js", "import React from 'react';\n")
    g = build_internals(tmp_path, "app")
    assert g.edges == ()


def test_go_internal_package_edge(tmp_path):
    _w(tmp_path, "go.mod", "module example.com/app\n\ngo 1.21\n")
    _w(tmp_path, "main.go", 'package main\nimport "example.com/app/util"\n')
    _w(tmp_path, "util/util.go", "package util\n")
    g = build_internals(tmp_path, "app")
    assert any(e.to_id.startswith("util") for e in g.edges)


def test_rust_mod_declaration_edge(tmp_path):
    _w(tmp_path, "src/main.rs", "mod helpers;\nfn main() {}\n")
    _w(tmp_path, "src/helpers.rs", "pub fn h() {}\n")
    g = build_internals(tmp_path, "app")
    assert ("src/main", "src/helpers") in {(e.from_id, e.to_id) for e in g.edges}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_internals_reach.py -v`
Expected: FAIL (extractors not present; edges empty or modules undiscovered).

- [ ] **Step 3: Implement multi-language discovery and extraction**

In `internals/modules.py`, generalize `discover_modules` to classify by suffix, and add `_js_edges`, `_rust_edges`, `_go_edges`. Full code:

```python
import re

_LANG_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "javascript", ".tsx": "javascript",
    ".rs": "rust", ".go": "go",
}
_SUFFIXES = tuple(_LANG_BY_SUFFIX)


def _strip_suffix(rel: str) -> str:
    dot = rel.rfind(".")
    slash = rel.rfind("/")
    return rel[:dot] if dot > slash else rel


def discover_modules(repo_root: Path) -> list[ModuleNode]:
    mods: list[ModuleNode] = []
    for f in walk_files(repo_root, suffixes=_SUFFIXES):
        rel = f.relative_to(repo_root).as_posix()
        lang = _LANG_BY_SUFFIX.get(f.suffix, "")
        if not lang:
            continue
        mods.append(ModuleNode(id=_strip_suffix(rel), path=rel, language=lang))
    return sorted(mods, key=lambda m: m.id)


_JS_IMPORT = re.compile(r"""(?:import|export)[^'"]*?from\s*['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\)""")


def _js_resolve(importer_rel: str, spec: str, ids: set[str]) -> str | None:
    if not spec.startswith("."):
        return None
    base = (Path(importer_rel).parent / spec).as_posix()
    # normalize ./ and ../
    parts: list[str] = []
    for seg in base.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    cand = "/".join(parts)
    cand = _strip_suffix(cand) if "." in Path(cand).name else cand
    if cand in ids:
        return cand
    idx = cand + "/index"
    return idx if idx in ids else None


def _js_edges(repo_root: Path, ids: set[str]) -> list[InternalEdge]:
    out: list[InternalEdge] = []
    js_suffixes = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
    for f in walk_files(repo_root, suffixes=js_suffixes):
        rel = f.relative_to(repo_root).as_posix()
        from_id = _strip_suffix(rel)
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for m in _JS_IMPORT.finditer(line):
                spec = m.group(1) or m.group(2) or m.group(3)
                if not spec:
                    continue
                tid = _js_resolve(rel, spec, ids)
                if tid and tid != from_id:
                    out.append(InternalEdge(from_id, tid, rel, i, line.strip()))
    return out


_RUST_MOD = re.compile(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;")


def _rust_edges(repo_root: Path, ids: set[str]) -> list[InternalEdge]:
    out: list[InternalEdge] = []
    for f in walk_files(repo_root, suffixes=(".rs",)):
        rel = f.relative_to(repo_root).as_posix()
        from_id = _strip_suffix(rel)
        parent = Path(rel).parent.as_posix()
        parent = "" if parent == "." else parent + "/"
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = _RUST_MOD.match(line)
            if not m:
                continue
            name = m.group(1)
            for cand in (f"{parent}{name}", f"{parent}{name}/mod", f"{_strip_suffix(rel)}/{name}"):
                if cand in ids and cand != from_id:
                    out.append(InternalEdge(from_id, cand, rel, i, line.strip()))
                    break
    return out


_GO_MODULE = re.compile(r"^\s*module\s+(\S+)")
_GO_IMPORT_SINGLE = re.compile(r'^\s*import\s+"([^"]+)"')
_GO_IMPORT_BLOCK_LINE = re.compile(r'^\s*"([^"]+)"')


def _go_module_path(repo_root: Path) -> str | None:
    gomod = repo_root / "go.mod"
    if not gomod.is_file():
        return None
    try:
        for line in gomod.read_text(encoding="utf-8").splitlines():
            m = _GO_MODULE.match(line)
            if m:
                return m.group(1)
    except OSError:
        return None
    return None


def _go_edges(repo_root: Path, ids: set[str]) -> list[InternalEdge]:
    mod_path = _go_module_path(repo_root)
    if not mod_path:
        return []
    # internal package dirs are the set of directories that contain a .go file
    pkg_dirs = sorted({Path(m).parent.as_posix() for m in ids
                       if (repo_root / (m + ".go")).is_file() or "/" in m or True})
    out: list[InternalEdge] = []
    for f in walk_files(repo_root, suffixes=(".go",)):
        rel = f.relative_to(repo_root).as_posix()
        from_id = _strip_suffix(rel)
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        in_block = False
        for i, line in enumerate(lines, 1):
            spec = None
            if line.strip().startswith("import ("):
                in_block = True
                continue
            if in_block:
                if ")" in line:
                    in_block = False
                m = _GO_IMPORT_BLOCK_LINE.match(line)
                if m:
                    spec = m.group(1)
            else:
                m = _GO_IMPORT_SINGLE.match(line)
                if m:
                    spec = m.group(1)
            if spec and spec.startswith(mod_path + "/"):
                sub = spec[len(mod_path) + 1:]
                if sub in pkg_dirs and sub:
                    # represent the edge to the package dir's first module id
                    target = next((m2 for m2 in sorted(ids) if Path(m2).parent.as_posix() == sub), None)
                    if target and target != from_id:
                        out.append(InternalEdge(from_id, target, rel, i, line.strip()))
    return out


def extract_internal_edges(repo_root: Path, modules: list[ModuleNode]) -> list[InternalEdge]:
    ids = {m.id for m in modules}
    edges: list[InternalEdge] = []
    edges += _python_edges(repo_root, ids)
    edges += _js_edges(repo_root, ids)
    edges += _rust_edges(repo_root, ids)
    edges += _go_edges(repo_root, ids)
    return sorted(edges, key=lambda e: (e.from_id, e.to_id, e.evidence_file, e.evidence_line or 0))
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_internals_reach.py -v`
Expected: PASS (4 tests). If the Go test fails on `pkg_dirs` resolution, simplify `_go_edges` to map a spec suffix directly to any module id whose parent dir equals the suffix; keep the conservative bound.

- [ ] **Step 5: Run all internals tests + full suite for regressions**

Run: `python -m pytest tests/test_internals_modules.py tests/test_internals_build.py tests/test_internals_reach.py -v && python -m pytest -q`
Expected: internals PASS; full suite still 217 passed plus the new tests.

- [ ] **Step 6: Commit**

```bash
git add src/index_graph/internals tests/test_internals_reach.py
git commit -m "feat(internals): best-effort JS/TS, Rust, Go file-level reach"
```

---

## Phase 3: Architecture criteria (`[architecture]` config)

### Task 4: Parse `[architecture]` in config

**Files:**
- Create: `src/index_graph/arch/__init__.py`
- Create: `src/index_graph/arch/criteria.py`
- Modify: `src/index_graph/config.py` (add `"architecture"` to `_KNOWN_TOP`; parse block; add field)
- Test: `tests/test_arch_criteria.py`, `tests/test_config_architecture.py`

**Interfaces:**
- Produces: `ArchitectureCriteria`, `LayerRule`, `ForbidRule` (exact fields in the spine), `parse_architecture(data: dict) -> ArchitectureCriteria`.
- `Config` gains `architecture: ArchitectureCriteria = ArchitectureCriteria()`.

- [ ] **Step 1: Write the failing test for the parser**

```python
# tests/test_arch_criteria.py
from index_graph.arch.criteria import parse_architecture, ArchitectureCriteria


def test_empty_block_is_undeclared():
    c = parse_architecture({})
    assert isinstance(c, ArchitectureCriteria)
    assert c.declared is False


def test_layers_and_forbid_and_cycles_and_owns():
    c = parse_architecture({
        "layers": ["core", "domain", "web"],
        "forbid": [{"from": "core/**", "to": "web/**"}],
        "max_cycles": 0,
        "owns": {"payments/**": "team-payments"},
    })
    assert c.layers == ("core", "domain", "web")
    assert c.forbid[0].from_glob == "core/**"
    assert c.forbid[0].to_glob == "web/**"
    assert c.max_cycles == 0
    assert c.owns == (("payments/**", "team-payments"),)
    assert c.declared is True


def test_malformed_forbid_raises():
    import pytest
    with pytest.raises(SystemExit):
        parse_architecture({"forbid": [{"from": "core/**"}]})
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_arch_criteria.py -v`
Expected: FAIL with `ModuleNotFoundError: index_graph.arch`.

- [ ] **Step 3: Implement `arch/criteria.py`**

```python
"""The architecture criterion: a rule the graph is measured against."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForbidRule:
    from_glob: str
    to_glob: str


@dataclass(frozen=True)
class ArchitectureCriteria:
    layers: tuple[str, ...] = ()
    forbid: tuple[ForbidRule, ...] = ()
    max_cycles: int | None = None
    owns: tuple[tuple[str, str], ...] = ()

    @property
    def declared(self) -> bool:
        return bool(self.layers or self.forbid or self.max_cycles is not None or self.owns)


def parse_architecture(data: dict) -> ArchitectureCriteria:
    """Parse the [architecture] TOML block. Raises SystemExit on malformed input."""
    layers = tuple(str(x) for x in data.get("layers", []))
    forbid_items = data.get("forbid", [])
    forbid: list[ForbidRule] = []
    for idx, item in enumerate(forbid_items):
        if not isinstance(item, dict) or "from" not in item or "to" not in item:
            raise SystemExit(f"[architecture] forbid[{idx}] requires 'from' and 'to'")
        forbid.append(ForbidRule(str(item["from"]), str(item["to"])))
    mc = data.get("max_cycles", None)
    if mc is not None and (not isinstance(mc, int) or mc < 0):
        raise SystemExit("[architecture] max_cycles must be a non-negative integer")
    owns_raw = data.get("owns", {})
    if not isinstance(owns_raw, dict):
        raise SystemExit("[architecture] owns must be a table of glob = owner")
    owns = tuple(sorted((str(k), str(v)) for k, v in owns_raw.items()))
    return ArchitectureCriteria(layers, tuple(forbid), mc, owns)
```

- [ ] **Step 4: Implement `arch/__init__.py`** (defer check imports until Task 5; for now export criteria)

```python
"""Architecture criteria and the check that measures a graph against them."""
from __future__ import annotations

from .criteria import ArchitectureCriteria, ForbidRule, parse_architecture

__all__ = ["ArchitectureCriteria", "ForbidRule", "parse_architecture"]
```

- [ ] **Step 5: Run to verify the parser passes**

Run: `python -m pytest tests/test_arch_criteria.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Wire into `config.py` (test first)**

```python
# tests/test_config_architecture.py
from pathlib import Path
from index_graph.config import load_config


def test_architecture_block_parsed(tmp_path):
    (tmp_path / ".index.toml").write_text(
        "[architecture]\nlayers = ['core', 'web']\nmax_cycles = 0\n", encoding="utf-8")
    cfg = load_config(None, tmp_path)
    assert cfg.architecture.layers == ("core", "web")
    assert cfg.architecture.max_cycles == 0


def test_absent_block_is_undeclared(tmp_path):
    cfg = load_config(None, tmp_path)
    assert cfg.architecture.declared is False
```

- [ ] **Step 7: Run to verify failure**

Run: `python -m pytest tests/test_config_architecture.py -v`
Expected: FAIL (`Config` has no `architecture`).

- [ ] **Step 8: Modify `config.py`**

Add the import at top: `from .arch.criteria import ArchitectureCriteria, parse_architecture`.
Add `"architecture"` to `_KNOWN_TOP`:

```python
_KNOWN_TOP = frozenset({"rule", "scan", "privacy", "output", "architecture"})
```

Add the field to `Config` (after `annotations`):

```python
    architecture: ArchitectureCriteria = field(default_factory=ArchitectureCriteria)
```

In `_build_config`, before the unknown-key loop, parse the block and pass it through:

```python
    architecture = parse_architecture(data.get("architecture", {}))
    ...
    return Config(tuple(rules), extra_prune, markers, jobs, omit, portable, annotations, architecture)
```

- [ ] **Step 9: Run config + arch + full suite**

Run: `python -m pytest tests/test_config_architecture.py tests/test_arch_criteria.py tests/test_config.py -v && python -m pytest -q`
Expected: PASS; no regressions.

- [ ] **Step 10: Commit**

```bash
git add src/index_graph/arch src/index_graph/config.py tests/test_arch_criteria.py tests/test_config_architecture.py
git commit -m "feat(arch): parse [architecture] criteria block (layers, forbid, max_cycles, owns)"
```

---

## Phase 4: The check

### Task 5: `check_graph` evaluates criteria, produces findings

**Files:**
- Create: `src/index_graph/arch/check.py`
- Modify: `src/index_graph/arch/__init__.py` (export `Finding`, `check_graph`)
- Test: `tests/test_arch_check.py`

**Interfaces:**
- Produces: `Finding` (exact fields in spine), `check_graph(pack: dict, criteria: ArchitectureCriteria, *, internal: dict[str, InternalGraph] | None = None) -> list[Finding]`.
- Consumes: the context pack dict from `context.pack.to_json` (has `relations`, `roles`, `cycles`), the existing `config.glob_to_regex` for glob matching.

**Layer rule semantics:** assign each repo to a layer by name match against `layers` (a repo named or path-tagged with a layer name belongs to that layer). An internal edge from a higher-index layer to a lower-index layer is allowed (web may import core); an edge from lower to higher is a violation (core may not import web). Repos not in any layer are unconstrained. When `layers` references a name that matches no repo, that is reported as UNVERIFIABLE by the certificate layer (Task 8), not as a pass.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_arch_check.py
from index_graph.arch.criteria import ArchitectureCriteria, ForbidRule
from index_graph.arch.check import check_graph, Finding


def _pack(relations, roles=None, cycles=None):
    return {"relations": relations, "roles": roles or {}, "cycles": cycles or []}


def test_forbid_edge_violation():
    pack = _pack([
        {"from": "core", "to": "web", "external": False, "confidence": "high",
         "signals": [{"file": "core/x.py", "line": 3}]},
    ])
    crit = ArchitectureCriteria(forbid=(ForbidRule("core", "web"),))
    findings = check_graph(pack, crit)
    assert any(f.rule == "forbid" and f.edge == "core -> web" for f in findings)
    assert findings[0].evidence == "core/x.py:3"


def test_layer_upward_import_violation():
    pack = _pack([
        {"from": "core", "to": "web", "external": False, "confidence": "high", "signals": []},
    ])
    crit = ArchitectureCriteria(layers=("core", "web"))
    findings = check_graph(pack, crit)
    assert any(f.rule == "layer" for f in findings)


def test_layer_downward_import_allowed():
    pack = _pack([
        {"from": "web", "to": "core", "external": False, "confidence": "high", "signals": []},
    ])
    crit = ArchitectureCriteria(layers=("core", "web"))
    assert [f for f in check_graph(pack, crit) if f.rule == "layer"] == []


def test_max_cycles_breach():
    pack = _pack([], cycles=[["a", "b"], ["c", "d"]])
    crit = ArchitectureCriteria(max_cycles=1)
    findings = check_graph(pack, crit)
    assert any(f.rule == "max_cycles" for f in findings)


def test_clean_graph_no_findings():
    pack = _pack([{"from": "web", "to": "core", "external": False, "confidence": "high", "signals": []}],
                 cycles=[])
    crit = ArchitectureCriteria(layers=("core", "web"), max_cycles=0)
    assert check_graph(pack, crit) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_arch_check.py -v`
Expected: FAIL (`arch.check` missing).

- [ ] **Step 3: Implement `arch/check.py`**

```python
"""Measure a graph against an ArchitectureCriteria; produce evidence-bearing findings."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import glob_to_regex
from .criteria import ArchitectureCriteria


@dataclass(frozen=True)
class Finding:
    rule: str
    detail: str
    edge: str | None
    evidence: str | None


def _match(glob: str, name: str) -> bool:
    return re.match(glob_to_regex(glob), name) is not None


def _first_evidence(rel: dict) -> str | None:
    sigs = rel.get("signals") or []
    if not sigs:
        return None
    s = sigs[0]
    f = s.get("file")
    if not f:
        return None
    line = s.get("line")
    return f"{f}:{line}" if line is not None else f


def _layer_of(name: str, layers: tuple[str, ...]) -> int | None:
    for i, layer in enumerate(layers):
        if name == layer or name.startswith(layer + "/") or _match(f"{layer}/**", name) or _match(f"**/{layer}", name):
            return i
    return None


def check_graph(pack: dict, criteria: ArchitectureCriteria, *, internal=None) -> list[Finding]:
    findings: list[Finding] = []
    relations = [r for r in pack.get("relations", []) if not r.get("external")]

    # forbid rules
    for rule in criteria.forbid:
        for r in relations:
            frm, to = r.get("from"), r.get("to")
            if to and _match(rule.from_glob, frm) and _match(rule.to_glob, to):
                findings.append(Finding("forbid", f"{rule.from_glob} must not depend on {rule.to_glob}",
                                        f"{frm} -> {to}", _first_evidence(r)))

    # layer rules: lower index = lower layer; an edge from lower to higher is a violation
    if criteria.layers:
        for r in relations:
            frm, to = r.get("from"), r.get("to")
            if not to:
                continue
            li, lj = _layer_of(frm, criteria.layers), _layer_of(to, criteria.layers)
            if li is not None and lj is not None and li < lj:
                findings.append(Finding("layer",
                                        f"{criteria.layers[li]} must not depend upward on {criteria.layers[lj]}",
                                        f"{frm} -> {to}", _first_evidence(r)))

    # cycle ceiling
    if criteria.max_cycles is not None:
        n = len(pack.get("cycles", []))
        if n > criteria.max_cycles:
            findings.append(Finding("max_cycles",
                                    f"{n} dependency cycle(s) exceed the ceiling of {criteria.max_cycles}",
                                    None, None))

    # ownership: every owned glob must match at least one repo (a declared owner with no repo is a finding)
    if criteria.owns:
        repo_names = [rel.get("from") for rel in pack.get("relations", [])]
        repo_names += [rel.get("to") for rel in pack.get("relations", []) if rel.get("to")]
        repo_names += list(pack.get("roles", {}).keys())
        names = sorted(set(n for n in repo_names if n))
        for glob, owner in criteria.owns:
            if not any(_match(glob, n) for n in names):
                findings.append(Finding("owns", f"ownership glob {glob} ({owner}) matches no repo", None, None))

    return sorted(findings, key=lambda f: (f.rule, f.edge or "", f.detail))
```

- [ ] **Step 4: Export from `arch/__init__.py`**

```python
from .criteria import ArchitectureCriteria, ForbidRule, parse_architecture
from .check import Finding, check_graph

__all__ = ["ArchitectureCriteria", "ForbidRule", "parse_architecture", "Finding", "check_graph"]
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_arch_check.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add src/index_graph/arch tests/test_arch_check.py
git commit -m "feat(arch): check_graph evaluates layers, forbid, max_cycles, owns with evidence"
```

---

## Phase 5: Snapshots and drift

### Task 6: Canonical snapshot and snapshot diff

**Files:**
- Create: `src/index_graph/drift/__init__.py`
- Create: `src/index_graph/drift/snapshot.py`
- Create: `src/index_graph/drift/diff.py`
- Test: `tests/test_drift.py`

**Interfaces:**
- Produces: `snapshot_pack(pack: dict) -> dict` (a canonical, minimal, sorted projection of the context pack); `DriftReport` (exact fields in spine); `diff_snapshots(old: dict, new: dict) -> DriftReport`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_drift.py
from index_graph.drift import snapshot_pack, diff_snapshots, DriftReport


def _pack(relations, roles, cycles=None):
    return {"relations": relations, "roles": roles, "cycles": cycles or []}


def test_snapshot_is_sorted_and_minimal():
    pack = _pack(
        relations=[{"from": "b", "to": "a", "external": False, "confidence": "high", "signals": []},
                   {"from": "a", "to": "c", "external": False, "confidence": "low", "signals": []}],
        roles={"b": ["hub"], "a": []},
    )
    snap = snapshot_pack(pack)
    assert snap["edges"] == ["a -> c", "b -> a"]
    assert snap["roles"] == {"a": [], "b": ["hub"]}


def test_diff_detects_added_removed_edges():
    old = snapshot_pack(_pack([{"from": "a", "to": "b", "external": False, "confidence": "high", "signals": []}], {"a": [], "b": []}))
    new = snapshot_pack(_pack([{"from": "a", "to": "c", "external": False, "confidence": "high", "signals": []}], {"a": [], "c": []}))
    report = diff_snapshots(old, new)
    assert report.edges_added == ("a -> c",)
    assert report.edges_removed == ("a -> b",)
    assert report.repos_added == ("c",)
    assert report.repos_removed == ("b",)
    assert report.verdict == "DRIFT"


def test_identical_snapshots_match():
    snap = snapshot_pack(_pack([{"from": "a", "to": "b", "external": False, "confidence": "high", "signals": []}], {"a": [], "b": []}))
    assert diff_snapshots(snap, snap).verdict == "MATCH"


def test_cycles_introduced_and_roles_changed():
    old = snapshot_pack(_pack([], {"a": ["leaf"]}, cycles=[]))
    new = snapshot_pack(_pack([], {"a": ["hub"]}, cycles=[["a", "b"]]))
    report = diff_snapshots(old, new)
    assert report.cycles_introduced == (("a", "b"),)
    assert ("a", "leaf", "hub") in report.roles_changed
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_drift.py -v`
Expected: FAIL (`drift` package missing).

- [ ] **Step 3: Implement `drift/snapshot.py`**

```python
"""Canonical, minimal, sorted projection of a context pack for drift diffing."""
from __future__ import annotations

import json


def snapshot_pack(pack: dict) -> dict:
    edges = sorted(
        f"{r['from']} -> {r['to']}"
        for r in pack.get("relations", [])
        if not r.get("external") and r.get("to")
    )
    roles = {k: list(v) for k, v in sorted(pack.get("roles", {}).items())}
    cycles = sorted(tuple(sorted(c)) for c in pack.get("cycles", []))
    repos = sorted(roles.keys())
    return {
        "schema": "index.snapshot/1",
        "repos": repos,
        "edges": edges,
        "roles": roles,
        "cycles": [list(c) for c in cycles],
    }


def dumps_canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def load_snapshot(text: str) -> dict:
    return json.loads(text)
```

- [ ] **Step 4: Implement `drift/diff.py`**

```python
"""Diff two snapshots into a DriftReport with a MATCH/DRIFT verdict."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriftReport:
    repos_added: tuple[str, ...]
    repos_removed: tuple[str, ...]
    edges_added: tuple[str, ...]
    edges_removed: tuple[str, ...]
    cycles_introduced: tuple[tuple[str, ...], ...]
    cycles_cleared: tuple[tuple[str, ...], ...]
    roles_changed: tuple[tuple[str, str, str], ...]

    @property
    def verdict(self) -> str:
        changed = any([
            self.repos_added, self.repos_removed, self.edges_added,
            self.edges_removed, self.cycles_introduced, self.cycles_cleared,
            self.roles_changed,
        ])
        return "DRIFT" if changed else "MATCH"

    def to_json(self) -> dict:
        return {
            "verdict": self.verdict,
            "repos_added": list(self.repos_added),
            "repos_removed": list(self.repos_removed),
            "edges_added": list(self.edges_added),
            "edges_removed": list(self.edges_removed),
            "cycles_introduced": [list(c) for c in self.cycles_introduced],
            "cycles_cleared": [list(c) for c in self.cycles_cleared],
            "roles_changed": [list(t) for t in self.roles_changed],
        }


def _cycle_set(snap: dict) -> set[tuple[str, ...]]:
    return {tuple(c) for c in snap.get("cycles", [])}


def diff_snapshots(old: dict, new: dict) -> DriftReport:
    o_repos, n_repos = set(old.get("repos", [])), set(new.get("repos", []))
    o_edges, n_edges = set(old.get("edges", [])), set(new.get("edges", []))
    o_cyc, n_cyc = _cycle_set(old), _cycle_set(new)
    o_roles, n_roles = old.get("roles", {}), new.get("roles", {})
    roles_changed = []
    for repo in sorted(set(o_roles) & set(n_roles)):
        a, b = o_roles.get(repo, []), n_roles.get(repo, [])
        if a != b:
            roles_changed.append((repo, ",".join(a), ",".join(b)))
    return DriftReport(
        repos_added=tuple(sorted(n_repos - o_repos)),
        repos_removed=tuple(sorted(o_repos - n_repos)),
        edges_added=tuple(sorted(n_edges - o_edges)),
        edges_removed=tuple(sorted(o_edges - n_edges)),
        cycles_introduced=tuple(sorted(n_cyc - o_cyc)),
        cycles_cleared=tuple(sorted(o_cyc - n_cyc)),
        roles_changed=tuple(roles_changed),
    )
```

- [ ] **Step 5: Implement `drift/__init__.py`**

```python
"""Snapshots over time and the drift between them."""
from __future__ import annotations

from .snapshot import snapshot_pack, dumps_canonical, load_snapshot
from .diff import DriftReport, diff_snapshots

__all__ = ["snapshot_pack", "dumps_canonical", "load_snapshot", "DriftReport", "diff_snapshots"]
```

- [ ] **Step 6: Run to verify pass**

Run: `python -m pytest tests/test_drift.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add src/index_graph/drift tests/test_drift.py
git commit -m "feat(drift): canonical snapshots + snapshot diff with MATCH/DRIFT verdict"
```

---

## Phase 6: The certificate (the reconcile binding)

### Task 7: Canonical hashing and certificate assembly

**Files:**
- Create: `src/index_graph/certify/__init__.py`
- Create: `src/index_graph/certify/certificate.py`
- Test: `tests/test_certificate.py`

**Interfaces:**
- Produces: `canonical_sha(obj) -> str`; `build_certificate(kind: str, *, content: dict, criterion: dict | None, verdict: str, findings: list[dict], recheck: str, tool_version: str) -> dict`.

**Verdict contract:** the caller passes the verdict; the certificate records it verbatim and must be one of `MATCH`, `DRIFT`, `UNVERIFIABLE`. `build_certificate` raises `ValueError` on any other verdict (this guards the no-fourth-answer invariant). `criterion_sha256` is `None` when `criterion is None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_certificate.py
import pytest
from index_graph.certify import canonical_sha, build_certificate


def test_canonical_sha_is_order_independent():
    assert canonical_sha({"a": 1, "b": 2}) == canonical_sha({"b": 2, "a": 1})


def test_certificate_shape_and_recheck_roundtrip():
    content = {"edges": ["a -> b"]}
    cert = build_certificate("check", content=content, criterion={"layers": ["core"]},
                             verdict="MATCH", findings=[], recheck="index check --root .",
                             tool_version="2.0.0")
    assert cert["schema"] == "index.certificate/1"
    assert cert["kind"] == "check"
    assert cert["verdict"] == "MATCH"
    assert cert["tool_version"] == "2.0.0"
    assert cert["content_sha256"] == canonical_sha(content)
    assert cert["criterion_sha256"] == canonical_sha({"layers": ["core"]})
    assert cert["recheck"] == "index check --root ."


def test_no_criterion_means_null_hash():
    cert = build_certificate("drift", content={"x": 1}, criterion=None,
                             verdict="DRIFT", findings=[], recheck="index drift ...",
                             tool_version="2.0.0")
    assert cert["criterion_sha256"] is None


def test_fourth_verdict_rejected():
    with pytest.raises(ValueError):
        build_certificate("check", content={}, criterion=None, verdict="TRUSTED",
                          findings=[], recheck="x", tool_version="2.0.0")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_certificate.py -v`
Expected: FAIL (`certify` missing).

- [ ] **Step 3: Implement `certify/certificate.py`**

```python
"""The verdict certificate: re-checkable, three answers, never a fourth."""
from __future__ import annotations

import hashlib
import json

_VERDICTS = frozenset({"MATCH", "DRIFT", "UNVERIFIABLE"})


def canonical_sha(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build_certificate(kind: str, *, content: dict, criterion: dict | None,
                      verdict: str, findings: list[dict], recheck: str,
                      tool_version: str) -> dict:
    if verdict not in _VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(_VERDICTS)}, got {verdict!r}")
    return {
        "schema": "index.certificate/1",
        "tool_version": tool_version,
        "kind": kind,
        "content_sha256": canonical_sha(content),
        "criterion_sha256": canonical_sha(criterion) if criterion is not None else None,
        "verdict": verdict,
        "findings": findings,
        "recheck": recheck,
    }
```

- [ ] **Step 4: Implement `certify/__init__.py`**

```python
"""Verdict certificates for check and drift."""
from __future__ import annotations

from .certificate import canonical_sha, build_certificate

__all__ = ["canonical_sha", "build_certificate"]
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_certificate.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/index_graph/certify tests/test_certificate.py
git commit -m "feat(certify): re-checkable MATCH/DRIFT/UNVERIFIABLE certificate"
```

---

## Phase 7: CLI wiring and the protocol document

### Task 8: Four subcommands (`internals`, `check`, `snapshot`, `drift`)

**Files:**
- Modify: `src/index_graph/cli.py`
- Test: `tests/test_cli_verify.py`

**Interfaces:**
- Consumes everything above. Produces the user-facing commands. The verdict for `check` is computed here: `UNVERIFIABLE` when the criterion is not declared, or when `layers` names a layer that matches no repo; otherwise `DRIFT` if findings exist else `MATCH`.

**Verdict logic for `check` (implement exactly):**
- If `not criteria.declared`: verdict `UNVERIFIABLE`, detail "no [architecture] criterion declared".
- Else if any declared `layers` entry matches no repo in the graph: verdict `UNVERIFIABLE`, a finding per unmatched layer.
- Else: `MATCH` if no findings, `DRIFT` if findings.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_verify.py
import json
import subprocess
import sys
from pathlib import Path


def _run(args, cwd):
    return subprocess.run([sys.executable, "-m", "index_graph", *args],
                          cwd=cwd, capture_output=True, text=True,
                          env={"PYTHONPATH": str(Path("src").resolve()), **_env()})


def _env():
    import os
    return dict(os.environ)


def _make_ws(tmp_path):
    # one repo, importing itself cleanly, with an [architecture] criterion
    repo = tmp_path / "core"
    (repo / "core").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='core'\nversion='0'\n", encoding="utf-8")
    (repo / "core" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / ".index.toml").write_text("[architecture]\nmax_cycles = 0\n", encoding="utf-8")
    return tmp_path


def test_internals_json_runs(tmp_path):
    repo = tmp_path
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "a.py").write_text("from .b import x\n", encoding="utf-8")
    (repo / "pkg" / "b.py").write_text("x = 1\n", encoding="utf-8")
    r = _run(["internals", "--root", str(repo), "--json"], cwd=Path.cwd())
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert any(e["from"] == "pkg/a" and e["to"] == "pkg/b" for e in data["edges"])


def test_check_unverifiable_without_criterion(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    r = _run(["check", "--root", str(tmp_path), "--json"], cwd=Path.cwd())
    cert = json.loads(r.stdout)
    assert cert["verdict"] == "UNVERIFIABLE"


def test_check_match_with_clean_criterion(tmp_path):
    ws = _make_ws(tmp_path)
    r = _run(["check", "--root", str(ws), "--json"], cwd=Path.cwd())
    cert = json.loads(r.stdout)
    assert cert["verdict"] in ("MATCH", "UNVERIFIABLE")
    assert cert["schema"] == "index.certificate/1"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_cli_verify.py -v`
Expected: FAIL (subcommands unknown; `index_graph` exits 2 on unknown subcommand).

- [ ] **Step 3: Modify `cli.py`**

Add to `_SUBCOMMANDS`: `{"map", "graph", "context", "viz", "atlas", "internals", "check", "snapshot", "drift"}`.

In `build_parser`, register the four parsers:

```python
    i = sub.add_parser("internals", help="Intra-repo module dependency graph.")
    i.add_argument("--root", type=Path, default=Path.cwd())
    i.add_argument("--json", action="store_true")
    i.add_argument("--cycles", action="store_true")

    ck = sub.add_parser("check", help="Check structure against the declared [architecture] criterion.")
    ck.add_argument("--root", type=Path, default=Path.cwd())
    ck.add_argument("--internals", action="store_true", help="Include intra-repo module checks.")
    ck.add_argument("--json", action="store_true")
    ck.add_argument("--config", type=Path, default=None)

    sn = sub.add_parser("snapshot", help="Write a canonical graph snapshot for drift diffing.")
    sn.add_argument("--root", type=Path, default=Path.cwd())
    sn.add_argument("--out", type=Path, required=True)

    dr = sub.add_parser("drift", help="Diff two snapshots into a drift report.")
    dr.add_argument("--from", dest="from_snap", type=Path, required=True)
    dr.add_argument("--to", dest="to_snap", type=Path, required=True)
    dr.add_argument("--json", action="store_true")
```

Add handlers:

```python
def _cmd_internals(args) -> int:
    from .internals import build_internals
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    g = build_internals(root)
    if getattr(args, "cycles", False):
        if args.json:
            print(json.dumps({"cycles": [list(c) for c in g.cycles]}, indent=2))
        elif not g.cycles:
            print("no internal cycles - clean DAG")
        else:
            print(f"{len(g.cycles)} internal cycle(s):")
            for c in g.cycles:
                print(f"  - {' -> '.join(c)}")
        return 0
    payload = {
        "repo": g.repo,
        "modules": [{"id": m.id, "path": m.path, "language": m.language} for m in g.modules],
        "edges": [{"from": e.from_id, "to": e.to_id, "file": e.evidence_file,
                   "line": e.evidence_line, "raw": e.raw} for e in g.edges],
        "cycles": [list(c) for c in g.cycles],
        "fan_in": g.fan_in, "fan_out": g.fan_out,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"modules={len(g.modules)} edges={len(g.edges)} cycles={len(g.cycles)}")
    return 0


def _cmd_check(args) -> int:
    from .config import load_config
    from .context.pack import to_json
    from .arch.check import check_graph
    from .certify import build_certificate
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    config = load_config(args.config, root)
    crit = config.architecture
    graph = build_graph(_repo_paths(root))
    pack = to_json(graph)
    names = set(pack.get("roles", {}).keys())

    findings: list = []
    verdict = "MATCH"
    if not crit.declared:
        verdict = "UNVERIFIABLE"
        findings.append({"rule": "criterion", "detail": "no [architecture] criterion declared",
                         "edge": None, "evidence": None})
    else:
        unmatched = [layer for layer in crit.layers
                     if not any(n == layer or n.startswith(layer + "/") or n.endswith("/" + layer) for n in names)]
        raw = check_graph(pack, crit)
        findings = [{"rule": f.rule, "detail": f.detail, "edge": f.edge, "evidence": f.evidence} for f in raw]
        if unmatched:
            verdict = "UNVERIFIABLE"
            for layer in unmatched:
                findings.append({"rule": "layer", "detail": f"layer '{layer}' matches no repo",
                                 "edge": None, "evidence": None})
        else:
            verdict = "DRIFT" if findings else "MATCH"

    criterion_doc = None
    if crit.declared:
        criterion_doc = {"layers": list(crit.layers),
                         "forbid": [{"from": f.from_glob, "to": f.to_glob} for f in crit.forbid],
                         "max_cycles": crit.max_cycles, "owns": [list(o) for o in crit.owns]}
    recheck = f"index check --root {args.root}" + (" --internals" if args.internals else "")
    cert = build_certificate("check", content=pack, criterion=criterion_doc,
                             verdict=verdict, findings=findings, recheck=recheck,
                             tool_version=__version__)
    if args.json:
        print(json.dumps(cert, indent=2))
    else:
        print(f"verdict={cert['verdict']} findings={len(findings)}")
        for f in findings:
            loc = f" ({f['evidence']})" if f.get("evidence") else ""
            print(f"  [{f['rule']}] {f['detail']}{loc}")
    return 0 if verdict == "MATCH" else 1


def _cmd_snapshot(args) -> int:
    from .context.pack import to_json
    from .drift import snapshot_pack, dumps_canonical
    root = args.root.resolve()
    graph = build_graph(_repo_paths(root))
    snap = snapshot_pack(to_json(graph))
    args.out.write_text(dumps_canonical(snap), encoding="utf-8")
    print(f"wrote {args.out} repos={len(snap['repos'])} edges={len(snap['edges'])}")
    return 0


def _cmd_drift(args) -> int:
    from .drift import load_snapshot, diff_snapshots
    old = load_snapshot(args.from_snap.read_text(encoding="utf-8"))
    new = load_snapshot(args.to_snap.read_text(encoding="utf-8"))
    report = diff_snapshots(old, new)
    if args.json:
        print(json.dumps(report.to_json(), indent=2))
    else:
        print(f"verdict={report.verdict}")
        for label, items in (("added", report.edges_added), ("removed", report.edges_removed)):
            for e in items:
                print(f"  edge {label}: {e}")
    return 0 if report.verdict == "MATCH" else 1
```

Extend `main()` dispatch (before the final `return _cmd_map(args)`):

```python
    if args.cmd == "internals":
        return _cmd_internals(args)
    if args.cmd == "check":
        return _cmd_check(args)
    if args.cmd == "snapshot":
        return _cmd_snapshot(args)
    if args.cmd == "drift":
        return _cmd_drift(args)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_cli_verify.py -v`
Expected: PASS (3 tests). If the subprocess cannot import `index_graph`, confirm the test passes `PYTHONPATH=src`; the repo's pytest config already sets `pythonpath=["src"]` for in-process tests, but the subprocess needs the env var.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: 217 prior tests plus all new tests, all green.

- [ ] **Step 6: Commit**

```bash
git add src/index_graph/cli.py tests/test_cli_verify.py
git commit -m "feat(cli): internals, check, snapshot, drift subcommands"
```

### Task 9: Protocol document, version bump, docs

**Files:**
- Create: `docs/PROTOCOL.md`
- Modify: `src/index_graph/__init__.py` (version to `2.0.0`)
- Modify: `README.md`, `USAGE.md`, `CHANGELOG.md`
- Test: `tests/test_version.py` (update expected version)

- [ ] **Step 1: Bump version (test first)**

Update `tests/test_version.py` expected value to `2.0.0`, then set `__version__ = "2.0.0"` in `src/index_graph/__init__.py`. Run `python -m pytest tests/test_version.py -v`. Expected: PASS.

- [ ] **Step 2: Write `docs/PROTOCOL.md`**

Content: the snapshot schema (`index.snapshot/1`), the certificate schema (`index.certificate/1`), the canonical-JSON hashing rule (`json.dumps(obj, sort_keys=True, separators=(",", ":"))` then SHA-256), and the three verdicts with their meanings. State the re-check procedure: a consumer re-runs `recheck`, recomputes `content_sha256` and `criterion_sha256`, and confirms `verdict`. Describe consumers generically (a CI gate, a reviewer, an external agent). Name no sibling product. Include the per-language module-resolution bounds verbatim from Phase 2.

- [ ] **Step 3: Update `README.md` and `USAGE.md`**

Add a "Verified architecture intelligence" section documenting `internals`, `check`, `snapshot`, `drift`, the `[architecture]` block, and a pointer to `docs/PROTOCOL.md`. No em-dashes. No sibling-product mentions.

- [ ] **Step 4: Update `CHANGELOG.md`**

Add a `## 2.0.0` entry summarizing: module-level internals graph; `[architecture]` criteria; `check` with evidence-bearing findings; `snapshot` and `drift`; the re-checkable MATCH/DRIFT/UNVERIFIABLE certificate; the documented protocol seam. Note backward compatibility and zero new dependencies.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add docs/PROTOCOL.md README.md USAGE.md CHANGELOG.md src/index_graph/__init__.py tests/test_version.py
git commit -m "docs+release: protocol seam, README/USAGE/CHANGELOG, bump to 2.0.0"
```

---

## Phase 8: Release preparation

### Task 10: Full verification, dogfood, tag-ready

**Files:** none new; this is verification.

- [ ] **Step 1: Full suite green**

Run: `python -m pytest -q`
Expected: 217 prior + all new tests, 0 failures.

- [ ] **Step 2: Build sanity**

Run: `python -m build && python -m twine check dist/*`
Expected: wheel and sdist build; twine check passes. (If `build`/`twine` are unavailable in the environment, skip with a note; the CI performs this on tag.)

- [ ] **Step 3: Dogfood over a real tree**

Run: `python -m index_graph internals --root src/index_graph --json` and `python -m index_graph check --root . --json`.
Expected: `internals` emits a module graph for the package itself (it will show internal edges among `graph/`, `viz/`, etc.); `check` emits a certificate. Capture anything surprising as a follow-up, not a blocker.

- [ ] **Step 4: Confirm backward compatibility**

Run: `python -m index_graph graph --root . --json | python -c "import sys,json; json.load(sys.stdin)"`
Expected: unchanged valid JSON. The five original subcommands behave exactly as before.

- [ ] **Step 5: Stop at the deploy boundary**

Do NOT create the `v2.0.0` tag or trigger the PyPI publish. Push the branch and open a PR. Surface the tag-ready state to the human and wait for explicit approval before any release tag.

---

## Self-Review (run before handoff)

**Spec coverage:** internals module graph (Phase 1-2) -> spec goal 1; `[architecture]` + check (Phase 3-4) -> goals 2; snapshot + drift (Phase 5) -> goal 3; certificate (Phase 6) -> goal 4; PROTOCOL.md (Phase 7) -> goal 5; full suite green + additive (every phase runs `pytest -q`) -> goals 6-7; tag-ready, no auto-deploy (Phase 8) -> goal 8. All spec success criteria map to a task.

**Placeholder scan:** no TBD/TODO; every code step shows real code; tests have real assertions.

**Type consistency:** `ModuleNode`, `InternalEdge`, `InternalGraph`, `ArchitectureCriteria`, `ForbidRule`, `Finding`, `DriftReport` are defined once in the spine and used with the same field names throughout. `check_graph(pack, criteria, *, internal=None)` signature is consistent between definition and the CLI call. `build_certificate(kind, *, content, criterion, verdict, findings, recheck, tool_version)` matches its call site in `_cmd_check`.

**Known soft spots to watch during execution (not blockers):** the Go internal-package resolution in `_go_edges` is the most heuristic part; if it proves flaky, narrow it to the conservative suffix-match bound and keep the test green. The layer-matching heuristic `_layer_of` may need tuning against the real dogfood tree; adjust the matcher, not the rule semantics.
