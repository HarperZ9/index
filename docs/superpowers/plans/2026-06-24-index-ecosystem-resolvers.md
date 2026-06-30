# index Ecosystem Resolvers (Rust, Go, Java) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Rust, Go, and Java dependency resolvers so workspaces in those ecosystems show inter-repo edges, each carrying evidence and a confidence grade, exactly as Python and JS do today.

**Architecture:** Three new resolver classes in the existing `graph/resolvers` seam (each implements `matches`/`exposed_names`/`raw_edges`), registered in `ALL_RESOLVERS`. One general enhancement to `resolve_edges`, a longest-prefix fallback, lets a Go import path resolve to its shorter module name. Everything is additive: `build_graph`, the pack, and all renderers are untouched.

**Tech Stack:** Python 3.11+ standard library only (`tomllib`, `xml.etree.ElementTree`, `re`), pytest.

## Global Constraints

Every task's requirements implicitly include this section. Values from `docs/superpowers/specs/2026-06-24-index-ecosystem-resolvers-design.md`.

- **Zero runtime dependencies.** Standard library only. The boundary test (`tests/test_viz_boundary.py`) and any import scan stay green; no third-party imports anywhere.
- **Deterministic.** Sorted collections; the same workspace gives the same graph and the same JSON.
- **Backward compatible, additive only.** The four `Edge` fields and every pack key are unchanged. Python and JS resolution is identical. The prefix fallback changes results only for targets that have no exact match today.
- **Real fixtures.** Each ecosystem adds tests against a tiny two-repo fixture (`a` depends on `b`), mirroring `tests/fixtures/py-app` and `py-lib`.
- **Confidence is earned, not asserted.** Rust and Go reach `high` only when a manifest and an import agree; Java is manifest-only, so `moderate`.
- **Commit trailer** (last line of every commit message): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Publish is operator-gated.** Do not push, tag, or publish.

**Repo:** `c:/dev/worktrees/wrm-rename`, branch `feat/v1.2-ecosystems` (off the published 1.1.0 @ `7c3d42a`). Full suite: `python -m pytest tests/ --color=no -q`.

---

## File Structure

**New source:**
- `src/index_graph/graph/resolvers/rust.py` -- `RustResolver` (Cargo.toml + use/extern-crate scan). (Task 2)
- `src/index_graph/graph/resolvers/go.py` -- `GoResolver` (go.mod + import scan). (Task 3)
- `src/index_graph/graph/resolvers/java.py` -- `JavaResolver` (Maven pom.xml + best-effort Gradle, manifest-only). (Task 4)

**Modified source:**
- `src/index_graph/graph/edges.py` -- add the longest-prefix fallback to `resolve_edges`. (Task 1)
- `src/index_graph/graph/resolvers/__init__.py` -- register each new resolver in `ALL_RESOLVERS`. (Tasks 2-4)
- `src/index_graph/__init__.py` -- version bump to 1.2.0. (Task 5)
- `CHANGELOG.md` -- add 1.1.0 and 1.2.0 entries. (Task 5)

**New tests + fixtures:**
- `tests/test_edges.py` -- prefix-fallback unit tests (modify). (Task 1)
- `tests/test_resolver_rust.py` + `tests/fixtures/rust-app/`, `rust-lib/`. (Task 2)
- `tests/test_resolver_go.py` + `tests/fixtures/go-app/`, `go-lib/`. (Task 3)
- `tests/test_resolver_java.py` + `tests/fixtures/java-app/`, `java-lib/`, `gradle-app/`. (Task 4)
- `tests/test_version.py`, `tests/test_cli.py`, `tests/test_viz_cli.py` -- version 1.1.0 to 1.2.0 (modify). (Task 5)

---

## Task 1: Longest-prefix fallback in `resolve_edges`

The enabling core change. Today `resolve_edges` matches a dependency name to a repo's exposed name exactly. Go modules are named `github.com/org/repo` but imported as `github.com/org/repo/pkg`, which is longer, so exact matching cannot connect an import to its module. Add a fallback: when a target contains `/` and has no exact match, resolve it to the longest exposed name that is a segment-aligned path prefix, and key the resulting edge by that canonical name so a `require` and an `import` of the same module merge into one high-confidence edge.

**Files:**
- Modify: `src/index_graph/graph/edges.py`
- Test: `tests/test_edges.py`

**Interfaces:**
- Consumes: `build_index`, `normalize_name`, `RawEdge` (existing).
- Produces: `resolve_edges` unchanged in signature; internally resolves slash-targets by longest prefix and keys edges by the canonical (matched) exposed name. Adds module-private `_resolve_target(index, norm_target) -> tuple[str, list[str]]`.

- [ ] **Step 1: Write the failing tests** -- append to `tests/test_edges.py`:

```python
def test_path_prefix_fallback_resolves_import_to_module():
    # Go-style: module "github.com/org/lib"; an import of a sub-package resolves to it,
    # and merges with the go.mod require into one high-confidence edge.
    index = build_index({"app": {"github.com/org/app"}, "lib": {"github.com/org/lib"}})
    raw = {"app": [
        RawEdge("github.com/org/lib", "manifest", "go.mod", None, "require github.com/org/lib v1"),
        RawEdge("github.com/org/lib/pkg/sub", "import", "app/main.go", 7, 'import "github.com/org/lib/pkg/sub"'),
    ]}
    edges, _ = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1
    e = internal[0]
    assert (e.from_repo, e.to_repo) == ("app", "lib")
    assert e.confidence == "high"                       # manifest + import agree
    assert e.target_name == "github.com/org/lib"        # canonical module, not the import path


def test_prefix_fallback_requires_segment_alignment():
    # "github.com/org/lib" must NOT match "github.com/org/libextra" (not a path prefix).
    index = build_index({"lib": {"github.com/org/lib"}})
    raw = {"app": [RawEdge("github.com/org/libextra", "import", "app/main.go", 1, "x")]}
    edges, _ = resolve_edges(raw, index)
    assert all(e.external for e in edges)               # no false prefix match


def test_exact_match_preferred_over_prefix():
    index = build_index({"lib": {"github.com/org/lib"}})
    raw = {"app": [RawEdge("github.com/org/lib", "import", "app/main.go", 1, "x")]}
    edges, _ = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1 and internal[0].to_repo == "lib"


def test_prefix_fallback_does_not_touch_slashless_names():
    # plain names (Python/JS) never enter the prefix path; behavior is identical.
    index = build_index({"a": {"a-pkg"}, "b": {"b-pkg"}})
    raw = {"a": [RawEdge("b-pkg", "manifest", "pyproject.toml", None, "b-pkg")]}
    edges, _ = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1 and internal[0].to_repo == "b"
```

- [ ] **Step 2: Run them, expect 1 FAIL** -- `test_path_prefix_fallback_resolves_import_to_module` fails (the two signals do not merge yet; the import is external).

Run: `python -m pytest tests/test_edges.py -q`
Expected: the new prefix-merge test FAILS; the other three may already pass.

- [ ] **Step 3: Add the fallback** -- in `src/index_graph/graph/edges.py`, add this helper above `resolve_edges`:

```python
def _resolve_target(index: dict[str, list[str]], norm_target: str) -> tuple[str, list[str]]:
    """Return (canonical_key, candidate_repos).

    Exact match wins. Otherwise, for a slash-containing target (a path-like name,
    e.g. a Go import path), fall back to the longest exposed name that is a
    segment-aligned prefix of the target. Unmatched targets keep their own name
    (they become external edges).
    """
    if norm_target in index:
        return norm_target, index[norm_target]
    if "/" in norm_target:
        best: str | None = None
        for key in index:
            if "/" in key and (norm_target == key or norm_target.startswith(key + "/")):
                if best is None or len(key) > len(best):
                    best = key
        if best is not None:
            return best, index[best]
    return norm_target, []
```

Then in `resolve_edges`, replace the candidate lookup and key construction. Change the line `candidates = index.get(normalize_name(r.target_name), [])` and the three `key = (..., normalize_name(r.target_name))` constructions to use the canonical key:

```python
    for frm, raws in repo_raw.items():
        for r in raws:
            canon, candidates = _resolve_target(index, normalize_name(r.target_name))
            internal = [c for c in candidates if c != frm]
            sig = Signal(r.signal, r.evidence_file, r.evidence_line, r.raw_spec)
            if not candidates:
                key = (frm, None, canon)                       # external
            elif not internal:
                continue                                       # self-edge only -> drop
            else:
                to = sorted(internal)[0]
                key = (frm, to, canon)
                if len(internal) > 1:
                    ambiguous_keys.add(key)
                    warnings.append(
                        f"ambiguous: {frm} -> {r.target_name!r} matches {sorted(internal)}")
            grouped.setdefault(key, []).append(sig)
```

(Only the lookup and the three keys change; the grading loop and sort below are untouched. `target` in the grading loop is now the canonical name, which is correct.)

- [ ] **Step 4: Run the edges tests, then the full suite** -- both green.

Run: `python -m pytest tests/test_edges.py -v && python -m pytest tests/ --color=no -q`
Expected: all PASS, including the pre-existing edges tests (exact-match behavior is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/graph/edges.py tests/test_edges.py
git commit -m "feat(edges): longest-prefix fallback so path-like deps (Go imports) resolve to their module

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Rust resolver (Cargo)

A `RustResolver` reading `Cargo.toml` for the crate name and its dependency tables, plus a `use` / `extern crate` scan of `.rs` files. Both signals match a workspace crate exactly after `-`/`_` unification, so Rust gets high-confidence edges.

**Files:**
- Create: `src/index_graph/graph/resolvers/rust.py`
- Modify: `src/index_graph/graph/resolvers/__init__.py`
- Test: `tests/test_resolver_rust.py`, `tests/fixtures/rust-app/*`, `tests/fixtures/rust-lib/*`

**Interfaces:**
- Consumes: `walk_files` (from `..walk`), `RawEdge` (from `.base`).
- Produces: `RustResolver` with `name = "rust"` and the `matches`/`exposed_names`/`raw_edges` protocol methods; added to `ALL_RESOLVERS`.

- [ ] **Step 1: Create the fixtures**

`tests/fixtures/rust-lib/Cargo.toml`:
```toml
[package]
name = "rust-lib"
version = "0.1.0"
```

`tests/fixtures/rust-lib/src/lib.rs`:
```rust
pub fn hello() -> u32 { 1 }
```

`tests/fixtures/rust-app/Cargo.toml`:
```toml
[package]
name = "rust-app"
version = "0.1.0"

[dependencies]
rust-lib = "0.1"
```

`tests/fixtures/rust-app/src/main.rs`:
```rust
use rust_lib::hello;
use crate::helpers::run;
mod helpers;

fn main() {
    let _ = hello();
    run();
}
```

`tests/fixtures/rust-app/src/helpers.rs`:
```rust
pub fn run() {}
```

- [ ] **Step 2: Write the failing tests** -- create `tests/test_resolver_rust.py`:

```python
from __future__ import annotations

from pathlib import Path

from index_graph.graph.build import build_graph
from index_graph.graph.resolvers import ALL_RESOLVERS
from index_graph.graph.resolvers.base import normalize_name
from index_graph.graph.resolvers.rust import RustResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed():
    r = RustResolver()
    assert r.matches(FIX / "rust-app") is True
    assert "rust-lib" in r.exposed_names(FIX / "rust-lib")


def test_raw_edges_manifest_and_import():
    edges = RustResolver().raw_edges(FIX / "rust-app")
    by = {(normalize_name(e.target_name), e.signal) for e in edges}
    assert ("rust-lib", "manifest") in by
    assert ("rust-lib", "import") in by                 # `use rust_lib` -> normalized rust-lib
    assert all(e.evidence_file for e in edges)
    imp = next(e for e in edges if e.signal == "import")
    assert imp.evidence_line is not None


def test_use_excludes_crate_self_super():
    targets = {normalize_name(e.target_name) for e in RustResolver().raw_edges(FIX / "rust-app")
               if e.signal == "import"}
    assert {"crate", "self", "super"}.isdisjoint(targets)


def test_rust_cross_repo_edge_is_high():
    g = build_graph({"rust-app": FIX / "rust-app", "rust-lib": FIX / "rust-lib"})
    e = [x for x in g.edges if x.from_repo == "rust-app" and x.to_repo == "rust-lib"]
    assert len(e) == 1 and e[0].confidence == "high"


def test_rust_registered():
    assert "rust" in {r.name for r in ALL_RESOLVERS}
```

- [ ] **Step 3: Run, expect FAIL** -- `ModuleNotFoundError: index_graph.graph.resolvers.rust`.

Run: `python -m pytest tests/test_resolver_rust.py -q`

- [ ] **Step 4: Implement the resolver** -- create `src/index_graph/graph/resolvers/rust.py`:

```python
"""Rust ecosystem resolver: Cargo.toml manifests + a use/extern-crate scan."""
from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_DEP_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")
_USE = re.compile(r"^\s*use\s+([A-Za-z_][A-Za-z0-9_]*)")
_EXTERN = re.compile(r"^\s*extern\s+crate\s+([A-Za-z_][A-Za-z0-9_]*)")
_INTRA = {"crate", "self", "super"}   # path roots that name the current crate, not a dep


class RustResolver:
    name = "rust"

    def matches(self, repo_root: Path) -> bool:
        return (repo_root / "Cargo.toml").is_file()

    def _manifests(self, repo_root: Path) -> Iterator[Path]:
        return walk_files(repo_root, names=("Cargo.toml",))

    def exposed_names(self, repo_root: Path) -> set[str]:
        names: set[str] = set()
        for ct in self._manifests(repo_root):
            try:
                data = tomllib.loads(ct.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, OSError):
                continue
            pkg = data.get("package", {})
            if isinstance(pkg, dict) and pkg.get("name"):
                names.add(str(pkg["name"]))
        return names

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []
        for ct in self._manifests(repo_root):
            try:
                data = tomllib.loads(ct.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, OSError):
                continue
            rel = ct.relative_to(repo_root).as_posix()
            for table in _DEP_TABLES:
                section = data.get(table, {})
                if isinstance(section, dict):
                    for name in section:
                        edges.append(RawEdge(str(name), "manifest", rel, None, f"{table}.{name}"))
        for src in walk_files(repo_root, suffixes=(".rs",)):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                m = _USE.match(line) or _EXTERN.match(line)
                if m and m.group(1) not in _INTRA:
                    edges.append(RawEdge(m.group(1), "import", rel, i, line.strip()))
        return edges
```

- [ ] **Step 5: Register it** -- in `src/index_graph/graph/resolvers/__init__.py`, add the import and extend `ALL_RESOLVERS`:

```python
"""Per-ecosystem dependency resolvers."""
from .javascript import JavaScriptResolver
from .python import PythonResolver
from .rust import RustResolver

ALL_RESOLVERS = (PythonResolver(), JavaScriptResolver(), RustResolver())
```

- [ ] **Step 6: Run the Rust tests + the full suite** -- all green.

Run: `python -m pytest tests/test_resolver_rust.py -v && python -m pytest tests/ --color=no -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/index_graph/graph/resolvers/rust.py src/index_graph/graph/resolvers/__init__.py tests/test_resolver_rust.py tests/fixtures/rust-app tests/fixtures/rust-lib
git commit -m "feat(resolvers): Rust (Cargo) resolver, manifest + use-scan, high-confidence edges

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Go resolver (go.mod)

A `GoResolver` reading `go.mod` for the module path and its `require` paths, plus an `import "path"` scan of `.go` files. A `require` path matches a module exactly; an import path is longer (module plus sub-package) and resolves via Task 1's prefix fallback. Both signals agreeing give a high-confidence edge.

**Files:**
- Create: `src/index_graph/graph/resolvers/go.py`
- Modify: `src/index_graph/graph/resolvers/__init__.py`
- Test: `tests/test_resolver_go.py`, `tests/fixtures/go-app/*`, `tests/fixtures/go-lib/*`

**Interfaces:**
- Consumes: `walk_files`, `RawEdge`, and Task 1's prefix fallback in `resolve_edges` (for the import second-signal).
- Produces: `GoResolver` with `name = "go"`; added to `ALL_RESOLVERS`.

- [ ] **Step 1: Create the fixtures**

`tests/fixtures/go-lib/go.mod`:
```text
module github.com/org/go-lib

go 1.21
```

`tests/fixtures/go-lib/sub/sub.go`:
```go
package sub

func Hello() int { return 1 }
```

`tests/fixtures/go-app/go.mod`:
```text
module github.com/org/go-app

go 1.21

require (
	github.com/org/go-lib v1.0.0
)
```

`tests/fixtures/go-app/main.go`:
```go
package main

import (
	"fmt"

	"github.com/org/go-lib/sub"
)

func main() {
	fmt.Println(sub.Hello())
}
```

- [ ] **Step 2: Write the failing tests** -- create `tests/test_resolver_go.py`:

```python
from __future__ import annotations

from pathlib import Path

from index_graph.graph.build import build_graph
from index_graph.graph.resolvers import ALL_RESOLVERS
from index_graph.graph.resolvers.go import GoResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed_module():
    r = GoResolver()
    assert r.matches(FIX / "go-app") is True
    assert "github.com/org/go-lib" in r.exposed_names(FIX / "go-lib")


def test_raw_edges_require_and_import():
    edges = GoResolver().raw_edges(FIX / "go-app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("github.com/org/go-lib", "manifest") in by         # from the require block
    assert ("github.com/org/go-lib/sub", "import") in by       # the sub-package import
    imp = next(e for e in edges if e.signal == "import" and e.target_name.endswith("/sub"))
    assert imp.evidence_line is not None


def test_go_cross_repo_edge_is_high_via_prefix():
    # the require (exact) and the sub-package import (prefix) merge to one high edge
    g = build_graph({"go-app": FIX / "go-app", "go-lib": FIX / "go-lib"})
    e = [x for x in g.edges if x.from_repo == "go-app" and x.to_repo == "go-lib"]
    assert len(e) == 1 and e[0].confidence == "high"


def test_go_registered():
    assert "go" in {r.name for r in ALL_RESOLVERS}
```

- [ ] **Step 3: Run, expect FAIL** -- `ModuleNotFoundError: index_graph.graph.resolvers.go`.

Run: `python -m pytest tests/test_resolver_go.py -q`

- [ ] **Step 4: Implement the resolver** -- create `src/index_graph/graph/resolvers/go.py`:

```python
"""Go ecosystem resolver: go.mod requires + an import-path scan."""
from __future__ import annotations

import re
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_MODULE = re.compile(r"^\s*module\s+(\S+)")
_REQUIRE_SINGLE = re.compile(r"^\s*require\s+(\S+)\s+\S+")
_IMPORT_SINGLE = re.compile(r'^\s*import\s+(?:[A-Za-z0-9_.]+\s+)?"([^"]+)"')
_GROUPED_IMPORT = re.compile(r'^\s*(?:[A-Za-z0-9_.]+\s+)?"([^"]+)"')


class GoResolver:
    name = "go"

    def matches(self, repo_root: Path) -> bool:
        return (repo_root / "go.mod").is_file()

    def exposed_names(self, repo_root: Path) -> set[str]:
        gm = repo_root / "go.mod"
        try:
            for line in gm.read_text(encoding="utf-8").splitlines():
                m = _MODULE.match(line)
                if m:
                    return {m.group(1)}
        except OSError:
            pass
        return set()

    def _require_paths(self, text: str) -> list[str]:
        out: list[str] = []
        in_block = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("require (") or s == "require (":
                in_block = True
                continue
            if in_block:
                if s == ")":
                    in_block = False
                elif s and not s.startswith("//"):
                    out.append(s.split()[0])
                continue
            m = _REQUIRE_SINGLE.match(line)
            if m:
                out.append(m.group(1))
        return out

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []
        gm = repo_root / "go.mod"
        if gm.is_file():
            try:
                for path in self._require_paths(gm.read_text(encoding="utf-8")):
                    edges.append(RawEdge(path, "manifest", "go.mod", None, f"require {path}"))
            except OSError:
                pass
        for src in walk_files(repo_root, suffixes=(".go",)):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            in_block = False
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if s.startswith("import ("):
                    in_block = True
                    continue
                if in_block:
                    if s == ")":
                        in_block = False
                        continue
                    m = _GROUPED_IMPORT.match(s)
                    if m:
                        edges.append(RawEdge(m.group(1), "import", rel, i, s))
                    continue
                m = _IMPORT_SINGLE.match(line)
                if m:
                    edges.append(RawEdge(m.group(1), "import", rel, i, s))
        return edges
```

- [ ] **Step 5: Register it** -- in `src/index_graph/graph/resolvers/__init__.py`, add `from .go import GoResolver` and append `GoResolver()` to `ALL_RESOLVERS`:

```python
ALL_RESOLVERS = (PythonResolver(), JavaScriptResolver(), RustResolver(), GoResolver())
```

- [ ] **Step 6: Run the Go tests + the full suite** -- all green.

Run: `python -m pytest tests/test_resolver_go.py -v && python -m pytest tests/ --color=no -q`

- [ ] **Step 7: Commit**

```bash
git add src/index_graph/graph/resolvers/go.py src/index_graph/graph/resolvers/__init__.py tests/test_resolver_go.py tests/fixtures/go-app tests/fixtures/go-lib
git commit -m "feat(resolvers): Go (go.mod) resolver, require + import scan via prefix fallback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Java resolver (Maven + best-effort Gradle)

A `JavaResolver` reading Maven `pom.xml` coordinates and dependencies (clean XML), plus a best-effort Gradle scan. Manifest-only: Java imports name packages, not artifacts, so there is no reliable import signal, and Java edges are `moderate`.

**Files:**
- Create: `src/index_graph/graph/resolvers/java.py`
- Modify: `src/index_graph/graph/resolvers/__init__.py`
- Test: `tests/test_resolver_java.py`, `tests/fixtures/java-app/*`, `tests/fixtures/java-lib/*`, `tests/fixtures/gradle-app/*`

**Interfaces:**
- Consumes: `walk_files`, `RawEdge`, `xml.etree.ElementTree`.
- Produces: `JavaResolver` with `name = "java"`; added to `ALL_RESOLVERS`.

- [ ] **Step 1: Create the fixtures**

`tests/fixtures/java-lib/pom.xml`:
```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>java-lib</artifactId>
  <version>1.0.0</version>
</project>
```

`tests/fixtures/java-app/pom.xml`:
```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>java-app</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>java-lib</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>
</project>
```

`tests/fixtures/gradle-app/build.gradle`:
```gradle
plugins {
    id 'java'
}

dependencies {
    implementation 'com.example:java-lib:1.0.0'
}
```

- [ ] **Step 2: Write the failing tests** -- create `tests/test_resolver_java.py`:

```python
from __future__ import annotations

from pathlib import Path

from index_graph.graph.build import build_graph
from index_graph.graph.resolvers import ALL_RESOLVERS
from index_graph.graph.resolvers.java import JavaResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_pom_and_gradle():
    r = JavaResolver()
    assert r.matches(FIX / "java-app") is True
    assert r.matches(FIX / "gradle-app") is True


def test_exposed_coordinates_from_pom():
    assert "com.example:java-lib" in JavaResolver().exposed_names(FIX / "java-lib")


def test_maven_dependency_edge():
    by = {(e.target_name, e.signal) for e in JavaResolver().raw_edges(FIX / "java-app")}
    assert ("com.example:java-lib", "manifest") in by


def test_gradle_dependency_edge():
    by = {(e.target_name, e.signal) for e in JavaResolver().raw_edges(FIX / "gradle-app")}
    assert ("com.example:java-lib", "manifest") in by


def test_java_cross_repo_edge_is_moderate():
    g = build_graph({"java-app": FIX / "java-app", "java-lib": FIX / "java-lib"})
    e = [x for x in g.edges if x.from_repo == "java-app" and x.to_repo == "java-lib"]
    assert len(e) == 1 and e[0].confidence == "moderate"     # manifest-only


def test_java_registered():
    assert "java" in {r.name for r in ALL_RESOLVERS}
```

- [ ] **Step 3: Run, expect FAIL** -- `ModuleNotFoundError: index_graph.graph.resolvers.java`.

Run: `python -m pytest tests/test_resolver_java.py -q`

- [ ] **Step 4: Implement the resolver** -- create `src/index_graph/graph/resolvers/java.py`:

```python
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
```

- [ ] **Step 5: Register it** -- in `src/index_graph/graph/resolvers/__init__.py`, add `from .java import JavaResolver` and append `JavaResolver()`:

```python
ALL_RESOLVERS = (PythonResolver(), JavaScriptResolver(), RustResolver(), GoResolver(), JavaResolver())
```

- [ ] **Step 6: Run the Java tests + the full suite + the boundary test** -- all green.

Run: `python -m pytest tests/test_resolver_java.py tests/test_viz_boundary.py -v && python -m pytest tests/ --color=no -q`
Expected: all PASS (the boundary test confirms the new resolvers import only stdlib + `index_graph`).

- [ ] **Step 7: Commit**

```bash
git add src/index_graph/graph/resolvers/java.py src/index_graph/graph/resolvers/__init__.py tests/test_resolver_java.py tests/fixtures/java-app tests/fixtures/java-lib tests/fixtures/gradle-app
git commit -m "feat(resolvers): Java resolver, Maven pom + best-effort Gradle, manifest-only

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: CHANGELOG + version 1.2.0

Add the missing 1.1.0 entry and the new 1.2.0 entry, and bump the version (with the three version-locked tests).

**Files:**
- Modify: `CHANGELOG.md`, `src/index_graph/__init__.py`
- Test: `tests/test_version.py`, `tests/test_cli.py`, `tests/test_viz_cli.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `__version__ = "1.2.0"`.

- [ ] **Step 1: Update the version-locked tests first (TDD: they should fail against the still-1.1.0 source)**

In `tests/test_version.py`, rename and update:
```python
def test_version_is_1_2_0():
    assert index_graph.__version__ == "1.2.0"
```
In `tests/test_cli.py`, in `test_version_flag_exits_zero`:
```python
    assert "1.2.0" in capsys.readouterr().out
```
In `tests/test_viz_cli.py`, rename and update:
```python
def test_version_is_1_2_0():
    from index_graph import __version__
    assert __version__ == "1.2.0"
```

- [ ] **Step 2: Run, expect 3 FAIL** (source is still 1.1.0)

Run: `python -m pytest tests/test_version.py tests/test_cli.py::test_version_flag_exits_zero tests/test_viz_cli.py -q`
Expected: the three version assertions FAIL.

- [ ] **Step 3: Bump the version** -- in `src/index_graph/__init__.py`, change `__version__ = "1.1.0"` to:
```python
__version__ = "1.2.0"
```

- [ ] **Step 4: Add the CHANGELOG entries** -- in `CHANGELOG.md`, insert these two sections directly below the top `# Changelog` line and above `## 1.0.0`:

```markdown
## 1.2.0

### Added
- Rust (`Cargo.toml`), Go (`go.mod`), and Java (Maven `pom.xml`, best-effort Gradle)
  dependency resolvers. Workspaces in these ecosystems now show inter-repo edges, each
  with evidence and a confidence grade. Rust and Go reach `high` confidence when a
  manifest and an import agree; Java is manifest-only (`moderate`).

### Changed
- `resolve_edges` gains a longest-prefix fallback for path-like dependency names, so a
  Go import of a module's sub-package resolves to that module. Python and JavaScript
  resolution is unchanged.

## 1.1.0

### Added
- `index atlas`: a two-layer code-and-knowledge map. Markdown docs become first-class
  nodes joined to the code they describe, rendered as one self-contained, navigable HTML
  dashboard (pan and zoom, unified repo and doc search, in-place rendered markdown with
  clickable `[[wiki-links]]`, focus, and a navigation trail).
- Dependency dashboard: cycle detection and highlighting, edge-evidence tooltips, a
  legend, and neighborhood highlighting. `index graph --cycles` reports dependency cycles.

### Changed
- License moved to fair source (FSL-1.1-MIT): source-available with a competing-use
  restriction, converting to MIT two years after each release. 1.0.0 remains MIT.
```

- [ ] **Step 5: Run the full suite** -- all green.

Run: `python -m pytest tests/ --color=no -q`
Expected: all PASS, version now 1.2.0.

- [ ] **Step 6: Commit**

```bash
git add src/index_graph/__init__.py CHANGELOG.md tests/test_version.py tests/test_cli.py tests/test_viz_cli.py
git commit -m "release: version 1.2.0 + CHANGELOG (1.1.0 and 1.2.0 entries)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after Task 5)

- [ ] **Full suite green:** `python -m pytest tests/ --color=no -q` -- the prior 197 plus the new resolver/edges tests, zero failures.
- [ ] **Boundary intact:** `python -m pytest tests/test_viz_boundary.py -v` -- the new resolvers add no third-party imports.
- [ ] **Existing ecosystems unchanged:** `python -m pytest tests/test_resolver_python.py tests/test_resolver_javascript.py tests/test_edges.py -v` -- Python and JS resolution and the pre-existing edge tests still pass.
- [ ] **Whole-branch review:** dispatch the opus final review per the subagent-driven cadence before declaring the sprint done. Publish stays operator-gated (the operator bumps nothing further; 1.2.0 is set, and the tag/publish is theirs).
