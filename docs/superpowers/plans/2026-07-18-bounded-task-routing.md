# Bounded Task Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, evidence-backed `index route` surface and make the existing workspace router honor explicit scope and work budgets instead of wedging its MCP host.

**Architecture:** A new `index_graph.route` package owns request validation, monotonic work budgets, scope selection, bounded document reads, incremental freshness manifests, cache entries, route receipts, and orchestration. Existing repository, graph, and freshness walkers gain optional cooperative checkpoints without changing their default exhaustive behavior. CLI, MCP, and Python call the same engine; the legacy Markdown router renders the same receipt without volatile timing fields.

**Tech Stack:** Python 3.11+, standard library only (`argparse`, `contextvars`, `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `re`, `time`, `typing`). `pytest>=8` for tests.

## Global Constraints

- Python floor remains **3.11**.
- Add **zero runtime dependencies**.
- Defaults are exactly `max_repos=12`, `max_docs=8`, `budget_ms=5000`, and `freshness="bounded"`.
- Supported freshness values are exactly `bounded` and `strict`.
- Supported route verdicts are exactly `MATCH`, `PARTIAL`, `STALE`, and `UNVERIFIABLE`.
- `MATCH` requires complete verified evidence for the declared scope.
- A cached result that cannot be completely revalidated is `STALE`, never `MATCH`.
- Bounded freshness may validate tracked file and directory metadata only.
- Strict freshness must recompute content digests and detect nested source edits
  (including same-size edits with restored timestamps) plus nested
  relevant-file additions.
- Explicit paths must resolve beneath `root`; escaping paths are rejected with `outside-root`.
- `max_docs` is an upper bound on document bodies opened by a route.
- Candidate accounting must reconcile as `candidates = selected + rejected + omitted`.
- Portable output contains root-relative paths only.
- CLI, MCP, and Python must call one route engine and emit `index.route-receipt/v1`.
- Existing exhaustive callers remain exhaustive when they do not pass a checkpoint.
- Existing `index_router` remains Markdown and retains its established workspace-map sections after a complete build.
- Structured receipts contain measured elapsed time; deterministic Markdown does not.
- No test or benchmark may invoke WSL.
- Use TDD for every production change: observe the targeted test fail for the intended reason before implementing.
- Preserve unrelated dirty work and stage only files named by the active task.

---

## Execution Preflight

Before Task 1, make the isolated worktree's `src` tree authoritative for every
CLI and subprocess check:

```text
python -m pip install -e ".[test]"
python -c "import index_graph, pathlib; print(pathlib.Path(index_graph.__file__).resolve())"
```

The printed path must be beneath
`C:/dev/worktrees/index-router-performance/src/index_graph`. Do not proceed if
Python resolves the canonical checkout or another installation.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/index_graph/route/__init__.py` | Public `build_route` export and route constants. |
| `src/index_graph/route/budget.py` | Monotonic `WorkBudget`, counters, and exhaustion boundary. |
| `src/index_graph/route/model.py` | Validated `RouteRequest`, typed route items, verdict and reconciliation helpers. |
| `src/index_graph/route/reads.py` | Shared root-contained `max_docs` body reader/cache. |
| `src/index_graph/route/scope.py` | Explicit-path validation, workspace-map candidate loading, deterministic scoring, bounded discovery. |
| `src/index_graph/route/documents.py` | Scoped deterministic Markdown enumeration and parsing through the shared reader. |
| `src/index_graph/route/freshness.py` | Tracked file/directory manifests and bounded/strict validation. |
| `src/index_graph/route/cache.py` | Constant-work cache identity and memory/disk route cache. |
| `src/index_graph/route/acceptance.py` | Testable hard-timeout child-command receipt helper. |
| `src/index_graph/route/engine.py` | Shared route orchestration and receipt construction. |
| `src/index_graph/cli_handlers/route.py` | `index route` and route-backed `index router` CLI handlers. |
| `src/index_graph/scan.py` | Optional repository-discovery checkpoint. |
| `src/index_graph/graph/walk.py` | Context-scoped cooperative checkpoint for existing resolver walks. |
| `src/index_graph/graph/build.py` | Optional graph-build checkpoint and partial-coverage warning. |
| `src/index_graph/freshness/fingerprint.py` | Public filename predicate and optional relevant-file checkpoint. |
| `src/index_graph/router.py` | Deterministic receipt preamble plus existing workspace-map renderer. |
| `src/index_graph/cli.py` | Register and dispatch `route`. |
| `src/index_graph/cli_parser.py` | Shared route controls for `route` and `router`. |
| `src/index_graph/mcp.py` | Register `index.route`, route before global discovery, and lazily discover repos for other tools. |
| `src/index_graph/flagship.py` | Advertise and doctor-probe the route surface. |
| `scripts/benchmark_route.py` | Non-gating JSON latency/work benchmark. |
| `scripts/verify_route_acceptance.py` | Hard-timeout CLI acceptance runner and artifact writer. |
| `tests/test_route_budget.py` | Budget and request validation. |
| `tests/test_route_traversal.py` | Cooperative traversal interruption and exhaustive-default compatibility. |
| `tests/test_route_scope.py` | Scope containment, map hints, scoring, limits, reconciliation. |
| `tests/test_route_documents.py` | Scoped enumeration and body-read limits. |
| `tests/test_route_cache.py` | Constant identity, manifests, cache corruption, nested drift. |
| `tests/test_route_engine.py` | End-to-end verdict, cache, budget, graph, and Markdown behavior. |
| `tests/test_route_cli.py` | CLI behavior and transport parity. |
| `tests/test_mcp.py` | MCP schema, lazy discovery, and route parity. |
| `README.md`, `USAGE.md`, `CHANGELOG.md` | Public behavior, examples, migration, and performance trade-off. |

---

### Task 1: Route request, budget, and reconciliation primitives

**Files:**
- Create: `src/index_graph/route/__init__.py`
- Create: `src/index_graph/route/budget.py`
- Create: `src/index_graph/route/model.py`
- Create: `src/index_graph/route/reads.py`
- Create: `tests/test_route_budget.py`

**Interfaces:**
- Produces: `RouteRequest.create(root, query="", paths=(), max_repos=12, max_docs=8, budget_ms=5000, freshness="bounded") -> RouteRequest`.
- Produces: mutable `WorkBudget.start(budget_ms, clock=time.monotonic)`,
  `checkpoint(boundary, counter=None, amount=1) -> bool`,
  `callback(counter=None) -> Callable[[str], bool]`, and `to_json() -> dict`.
- Produces: `route_item(path, reason_code, rule_ref, **evidence) -> dict`.
- Produces: `reconcile_route(candidates, selected, rejected, omitted) -> dict`.
- Produces: `DocumentReader(root, max_docs, budget).read(path) -> str | None`,
  `.reason(path) -> str | None`, and `.bodies() -> dict[str, str]`.

- [ ] **Step 1: Write failing request and budget tests**

Create `tests/test_route_budget.py`:

```python
from pathlib import Path

import pytest

from index_graph.route.budget import WorkBudget
from index_graph.route.model import RouteRequest, reconcile_route, route_item
from index_graph.route.reads import DocumentReader


def test_route_request_defaults_and_normalization(tmp_path):
    request = RouteRequest.create(tmp_path, query="  repair index  ", paths=["public/index"])
    assert request.root == tmp_path.resolve()
    assert request.query == "repair index"
    assert request.paths == ("public/index",)
    assert request.max_repos == 12
    assert request.max_docs == 8
    assert request.budget_ms == 5000
    assert request.freshness == "bounded"


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_repos", -1), ("max_docs", -1), ("budget_ms", 0), ("freshness", "eventual")],
)
def test_route_request_rejects_invalid_controls(tmp_path, field, value):
    kwargs = {field: value}
    with pytest.raises(ValueError, match=field):
        RouteRequest.create(tmp_path, **kwargs)


def test_work_budget_records_first_exhaustion_boundary():
    ticks = iter((10.000, 10.004, 10.006, 10.007))
    budget = WorkBudget.start(5, clock=lambda: next(ticks))
    assert budget.checkpoint("scope.repo", counter="repositories_visited") is True
    assert budget.checkpoint("docs.open", counter="document_bodies_opened") is False
    assert budget.exhausted_at == "docs.open"
    assert budget.checkpoint("graph.repo") is False
    receipt = budget.to_json()
    assert receipt["repositories_visited"] == 1
    assert receipt["document_bodies_opened"] == 0


def test_route_reconciliation_detects_no_silent_drop():
    candidates = ["public/index", "public/forum"]
    selected = ["public/index"]
    rejected = []
    omitted = [route_item("public/forum", "max-repos", "route.max_repos:1")]
    report = reconcile_route(candidates, selected, rejected, omitted)
    assert report["verdict"] == "MATCH"
    assert report["counts"] == {
        "candidates": 2,
        "selected": 1,
        "rejected": 0,
        "omitted": 1,
    }


def test_document_reader_enforces_global_body_cap_and_reuses_body(tmp_path):
    first = tmp_path / "README.md"
    second = tmp_path / "OTHER.md"
    first.write_text("# Index\n", encoding="utf-8")
    second.write_text("# Other\n", encoding="utf-8")
    budget = WorkBudget.start(5000)
    reader = DocumentReader(tmp_path, 1, budget)
    assert reader.read(first) == "# Index\n"
    assert reader.read(first) == "# Index\n"
    assert reader.read(second) is None
    assert reader.reason(second) == "max-docs"
    assert reader.bodies() == {"README.md": "# Index\n"}
    assert budget.counters["document_bodies_opened"] == 1
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```text
python -m pytest tests/test_route_budget.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'index_graph.route'`.

- [ ] **Step 3: Implement `WorkBudget`**

Create `src/index_graph/route/budget.py`:

```python
"""Monotonic cooperative work budgets for bounded routing."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Callable


_COUNTERS = (
    "repositories_visited",
    "directories_visited",
    "candidate_documents_observed",
    "document_bodies_opened",
    "files_validated",
)


@dataclass
class WorkBudget:
    requested_ms: int
    started_at: float
    deadline: float
    clock: Callable[[], float] = field(repr=False)
    counters: dict[str, int] = field(
        default_factory=lambda: {name: 0 for name in _COUNTERS}
    )
    exhausted_at: str | None = None

    @classmethod
    def start(
        cls, budget_ms: int, *, clock: Callable[[], float] = monotonic
    ) -> "WorkBudget":
        if budget_ms < 1:
            raise ValueError("budget_ms must be >= 1")
        started = clock()
        return cls(budget_ms, started, started + budget_ms / 1000, clock)

    def checkpoint(
        self, boundary: str, *, counter: str | None = None, amount: int = 1
    ) -> bool:
        if self.exhausted_at is not None or self.clock() >= self.deadline:
            self.exhausted_at = self.exhausted_at or boundary
            return False
        if counter is not None:
            if counter not in self.counters:
                raise ValueError(f"unknown budget counter: {counter}")
            self.counters[counter] += amount
        return True

    def callback(self, counter: str | None = None):
        return lambda boundary: self.checkpoint(boundary, counter=counter)

    @property
    def exhausted(self) -> bool:
        return self.exhausted_at is not None

    def to_json(self) -> dict:
        elapsed_ms = max(0, round((self.clock() - self.started_at) * 1000))
        return {
            "requested_ms": self.requested_ms,
            "elapsed_ms": elapsed_ms,
            **self.counters,
            "exhausted_at": self.exhausted_at,
        }
```

- [ ] **Step 4: Implement the shared document-body reader**

Create `src/index_graph/route/reads.py`. `DocumentReader` resolves every path,
rejects paths outside `root`, and keys its cache by portable root-relative
path. A cache hit returns the stored body without consuming a counter. A first
read is allowed only when fewer than `max_docs` distinct bodies are cached and
`budget.checkpoint("docs.open", counter="document_bodies_opened")` succeeds.
Read UTF-8 with replacement; return `None` on `OSError`, cap exhaustion, or
budget exhaustion, and store the stable failure reason for `reason(path)`.
`bodies()` returns a copy of the relative-path/body map so scope, document
parsing, graph descriptions, and manifest construction share the same reads
without mutation.

- [ ] **Step 5: Implement request and reconciliation types**

Create `src/index_graph/route/model.py`:

```python
"""Validated route requests and closed-world route receipts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ROUTE_SCHEMA = "index.route-receipt/v1"
DEFAULT_MAX_REPOS = 12
DEFAULT_MAX_DOCS = 8
DEFAULT_BUDGET_MS = 5000
FRESHNESS_MODES = frozenset({"bounded", "strict"})
VERDICTS = frozenset({"MATCH", "PARTIAL", "STALE", "UNVERIFIABLE"})
REASON_CODES = frozenset({
    "outside-root",
    "not-found",
    "not-repository",
    "unreadable",
    "duplicate",
    "max-repos",
    "max-docs",
    "budget-exhausted",
    "stale-manifest",
})


@dataclass(frozen=True)
class RouteRequest:
    root: Path
    query: str
    paths: tuple[str, ...]
    max_repos: int
    max_docs: int
    budget_ms: int
    freshness: str

    @classmethod
    def create(
        cls,
        root: Path | str,
        *,
        query: str = "",
        paths: Sequence[str] = (),
        max_repos: int = DEFAULT_MAX_REPOS,
        max_docs: int = DEFAULT_MAX_DOCS,
        budget_ms: int = DEFAULT_BUDGET_MS,
        freshness: str = "bounded",
    ) -> "RouteRequest":
        if max_repos < 0:
            raise ValueError("max_repos must be >= 0")
        if max_docs < 0:
            raise ValueError("max_docs must be >= 0")
        if budget_ms < 1:
            raise ValueError("budget_ms must be >= 1")
        if freshness not in FRESHNESS_MODES:
            raise ValueError("freshness must be bounded or strict")
        normalized = tuple(dict.fromkeys(str(path).replace("\\", "/") for path in paths))
        return cls(
            Path(root).resolve(),
            query.strip(),
            normalized,
            max_repos,
            max_docs,
            budget_ms,
            freshness,
        )


def route_item(path: str, reason_code: str, rule_ref: str, **evidence) -> dict:
    if reason_code not in REASON_CODES:
        raise ValueError(f"unknown route reason_code: {reason_code}")
    return {
        "path": path,
        "reason_code": reason_code,
        "rule_ref": rule_ref,
        "evidence": evidence,
    }


def reconcile_route(
    candidates: Iterable[str],
    selected: Iterable[str],
    rejected: Iterable[dict],
    omitted: Iterable[dict],
) -> dict:
    candidate_list = list(candidates)
    selected_list = list(selected)
    rejected_list = list(rejected)
    omitted_list = list(omitted)
    booked = selected_list + [item["path"] for item in rejected_list + omitted_list]
    failures = []
    if sorted(candidate_list) != sorted(booked):
        failures.append({
            "code": "candidate-accounting",
            "detail": "candidates must equal selected + rejected + omitted",
        })
    if len(booked) != len(set(booked)):
        failures.append({"code": "duplicate-booking", "detail": "a path was booked twice"})
    return {
        "verdict": "MATCH" if not failures else "DRIFT",
        "counts": {
            "candidates": len(candidate_list),
            "selected": len(selected_list),
            "rejected": len(rejected_list),
            "omitted": len(omitted_list),
        },
        "failures": failures,
    }
```

Create `src/index_graph/route/__init__.py`:

```python
"""Bounded, receipt-backed task routing."""

from .model import (
    DEFAULT_BUDGET_MS,
    DEFAULT_MAX_DOCS,
    DEFAULT_MAX_REPOS,
    ROUTE_SCHEMA,
    RouteRequest,
)

__all__ = [
    "DEFAULT_BUDGET_MS",
    "DEFAULT_MAX_DOCS",
    "DEFAULT_MAX_REPOS",
    "ROUTE_SCHEMA",
    "RouteRequest",
]
```

- [ ] **Step 6: Run GREEN and commit**

Run:

```text
python -m pytest tests/test_route_budget.py -q
python -m pytest tests/test_route_budget.py tests/test_mcp.py -q
git diff --check
```

Expected: all selected tests pass and `git diff --check` emits nothing.

Commit:

```text
git add src/index_graph/route tests/test_route_budget.py
git commit -m "feat(route): add budget and receipt primitives"
```

---

### Task 2: Cooperative checkpoints in existing traversal primitives

**Files:**
- Modify: `src/index_graph/scan.py`
- Modify: `src/index_graph/graph/walk.py`
- Modify: `src/index_graph/graph/build.py`
- Modify: `src/index_graph/freshness/fingerprint.py`
- Create: `tests/test_route_traversal.py`

**Interfaces:**
- `discover_repos(..., checkpoint: Callable[[str], bool] | None = None,
  prune_repo_contents: bool = False)` remains exhaustive by default.
- `walk_budget(checkpoint)` context manager scopes existing resolver walks.
- `build_graph(..., checkpoint: Callable[[str], bool] | None = None,
  document_reader: Callable[[Path], str | None] | None = None)` records
  the exact first failed boundary as `budget-exhausted:<boundary>` in warnings
  when partial.
- `is_relevant_filename(filename, resolvers=ALL_RESOLVERS) -> bool`.
- `relevant_files(..., checkpoint: Callable[[str], bool] | None = None)` remains exhaustive by default.

- [ ] **Step 1: Write failing traversal compatibility tests**

Create `tests/test_route_traversal.py`:

```python
from index_graph.config import default_config
from index_graph.freshness.fingerprint import relevant_files
from index_graph.graph.build import build_graph
from index_graph.graph.walk import walk_budget, walk_files
from index_graph.scan import discover_repos


def _tree(root):
    for index in range(6):
        repo = root / f"repo-{index}"
        (repo / ".git").mkdir(parents=True)
        (repo / "src").mkdir()
        (repo / "src" / f"mod{index}.py").write_text("x = 1\n", encoding="utf-8")


def test_discover_repos_checkpoint_stops_new_work(tmp_path):
    _tree(tmp_path)
    calls = []

    def checkpoint(boundary):
        calls.append(boundary)
        return len(calls) < 4

    repos = discover_repos(tmp_path, default_config(), checkpoint=checkpoint)
    assert len(repos) < 6
    assert calls[-1] == "scan.directory"


def test_walk_files_is_exhaustive_without_checkpoint(tmp_path):
    _tree(tmp_path)
    assert len(list(walk_files(tmp_path, suffixes=(".py",)))) == 6


def test_walk_budget_stops_existing_resolver_walk(tmp_path):
    _tree(tmp_path)
    calls = []

    def checkpoint(boundary):
        calls.append(boundary)
        return len(calls) < 3

    with walk_budget(checkpoint):
        found = list(walk_files(tmp_path, suffixes=(".py",)))
    assert len(found) < 6
    assert "graph.walk.directory" in calls


def test_relevant_files_checkpoint_and_default_compatibility(tmp_path):
    _tree(tmp_path)
    assert len(list(relevant_files(tmp_path))) == 6
    calls = []
    bounded = list(
        relevant_files(
            tmp_path,
            checkpoint=lambda boundary: calls.append(boundary) is None and len(calls) < 3,
        )
    )
    assert len(bounded) < 6


def test_build_graph_marks_budget_exhaustion(tmp_path):
    _tree(tmp_path)
    calls = []

    def checkpoint(boundary):
        calls.append(boundary)
        return boundary != "graph.repo"

    graph = build_graph(
        {f"repo-{i}": tmp_path / f"repo-{i}" for i in range(6)},
        checkpoint=checkpoint,
    )
    assert graph.warnings[-1] == "budget-exhausted:graph.repo"
    assert calls == ["graph.repo"]


def test_build_graph_uses_supplied_document_reader(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    readme = repo / "README.md"
    readme.write_text("# Repo\n\nExpected description.\n", encoding="utf-8")
    seen = []

    def reader(path):
        seen.append(path)
        return path.read_text(encoding="utf-8")

    graph = build_graph({"repo": repo}, document_reader=reader)
    assert readme in seen
    assert graph.repos[0].description == "Expected description."
```

- [ ] **Step 2: Run RED**

Run:

```text
python -m pytest tests/test_route_traversal.py -q
```

Expected: failures report unexpected `checkpoint` arguments and missing `walk_budget`.

- [ ] **Step 3: Add the scoped graph-walk checkpoint**

In `src/index_graph/graph/walk.py`, add:

```python
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

Checkpoint = Callable[[str], bool]
_ACTIVE_CHECKPOINT: ContextVar[Checkpoint | None] = ContextVar(
    "index_graph_walk_checkpoint", default=None
)


@contextmanager
def walk_budget(checkpoint: Checkpoint | None):
    token = _ACTIVE_CHECKPOINT.set(checkpoint)
    try:
        yield
    finally:
        _ACTIVE_CHECKPOINT.reset(token)


def _continue(boundary: str) -> bool:
    checkpoint = _ACTIVE_CHECKPOINT.get()
    return checkpoint is None or checkpoint(boundary)
```

Inside `walk_files`, before processing each `os.walk` result:

```python
        if not _continue("graph.walk.directory"):
            return
```

Before yielding each matching file:

```python
            if not _continue("graph.walk.file"):
                return
```

- [ ] **Step 4: Add optional checkpoints to discovery and freshness**

Change `discover_repos` in `src/index_graph/scan.py`:

```python
def discover_repos(
    root: Path,
    config: Config,
    *,
    skipped: list | None = None,
    checkpoint: Callable[[str], bool] | None = None,
    prune_repo_contents: bool = False,
) -> list[Path]:
```

At the start of each walk iteration:

```python
        if checkpoint is not None and not checkpoint("scan.directory"):
            dirnames.clear()
            break
```

When `prune_repo_contents=True` and the current directory contains a `.git`
file or directory, record that repository and clear `dirnames` after applying
the current checkpoint. The route discovery call uses this mode so observing
a repository root does not recursively visit its entire working tree before
selection. Existing callers retain `False` and their exhaustive behavior.

In `src/index_graph/freshness/fingerprint.py`, expose:

```python
def is_relevant_filename(filename: str, resolvers=ALL_RESOLVERS) -> bool:
    names, suffixes, globs = _matchers(resolvers)
    return _is_relevant(filename, names, suffixes, globs)
```

Change `relevant_files` to accept `checkpoint=None`, checking
`freshness.directory` before each directory and `freshness.file` before each
yield. With no checkpoint, behavior is unchanged.

In all three filesystem walkers (`discover_repos`, `walk_files`, and
`relevant_files`), sort the retained `dirnames` in place and iterate sorted
`filenames`. Exhaustive callers still receive the same set, while a budgeted
prefix becomes deterministic across filesystems instead of depending on
`os.walk` enumeration order. Add an order assertion with directories/files
created in reverse lexical order.

- [ ] **Step 5: Make graph construction report partial work**

Change the signature in `src/index_graph/graph/build.py`:

```python
def build_graph(
    repo_paths: dict[str, Path],
    resolvers=ALL_RESOLVERS,
    *,
    checkpoint=None,
    document_reader=None,
) -> DependencyGraph:
```

Wrap the repository/resolver loop with `walk_budget(checkpoint)`. Before each
repository and resolver call, invoke `checkpoint("graph.repo")` and
`checkpoint("graph.resolver")`. Stop starting new work after the first `False`.
Inside `build_graph`, wrap the caller callback in a local `checked(boundary)`
function that stores the first `False` boundary in
`exhausted_boundary`. Use `checked` for the direct repo/resolver checks and
pass that same wrapper to `walk_budget`, so an interruption inside an existing
resolver walk is observable by the builder. After `resolve_edges`, append exactly
`f"budget-exhausted:{exhausted_boundary}"` to warnings when interrupted. A
failed nested walk callback is reported by having the context-scoped wrapper
record its boundary into the same local capture; it must not degrade to a
generic `budget-exhausted:graph` warning.

Extend `_description(repo_root, document_reader=None)` so its default path is
byte-for-byte compatible, while a supplied reader is used for README Markdown.
The route engine supplies the shared capped reader from Task 4. Package
manifest description fallbacks remain unchanged because they are not document
bodies. This prevents graph metadata extraction from silently opening README
bodies beyond `max_docs`.

When the route engine supplies these callbacks, use
`budget.callback("directories_visited")` for directory walks and
`budget.callback("repositories_visited")` for repository-start boundaries so
the receipt counts only work units that actually began.

- [ ] **Step 6: Run GREEN, compatibility suite, and commit**

Run:

```text
python -m pytest tests/test_route_traversal.py tests/test_build.py tests/test_freshness.py -q
python -m pytest tests/test_router.py tests/test_mcp.py -q
git diff --check
```

Expected: all selected tests pass; existing exhaustive tests retain their counts.

Commit:

```text
git add src/index_graph/scan.py src/index_graph/graph/walk.py src/index_graph/graph/build.py src/index_graph/freshness/fingerprint.py tests/test_route_traversal.py
git commit -m "feat(route): bound filesystem traversal"
```

---

### Task 3: Scope resolution and deterministic query scoring

**Files:**
- Create: `src/index_graph/route/scope.py`
- Create: `tests/test_route_scope.py`

**Interfaces:**
- Produces `RepoCandidate(id, path, rel_path, source, score, signals)`.
- Produces
  `ScopeResult(candidates, selected, rejected, omitted, complete, source)`.
- Produces
  `resolve_scope(request, budget, *, reader: DocumentReader | None = None) -> ScopeResult`.
- Explicit paths never call workspace-map loading or global discovery.
- No more than `max_repos` candidates receive filesystem validation or
  README/config enrichment.

- [ ] **Step 1: Write failing scope tests**

Create `tests/test_route_scope.py`:

```python
import hashlib
import json

from index_graph.route.budget import WorkBudget
from index_graph.route.model import RouteRequest
from index_graph.route.scope import resolve_scope


def _repo(root, rel):
    repo = root / rel
    (repo / ".git").mkdir(parents=True)
    return repo


def test_explicit_path_is_root_relative_and_avoids_siblings(tmp_path):
    _repo(tmp_path, "public/index")
    _repo(tmp_path, "public/forum")
    request = RouteRequest.create(tmp_path, paths=["public/index"])
    result = resolve_scope(request, WorkBudget.start(5000))
    assert [candidate.id for candidate in result.selected] == ["public/index"]
    assert [candidate.id for candidate in result.candidates] == ["public/index"]


def test_explicit_dot_selects_repository_at_root(tmp_path):
    (tmp_path / ".git").mkdir()
    request = RouteRequest.create(tmp_path, paths=["."])
    result = resolve_scope(request, WorkBudget.start(5000))
    assert [candidate.id for candidate in result.selected] == ["."]


def test_explicit_paths_are_deduplicated_and_sorted(tmp_path):
    _repo(tmp_path, "public/b")
    _repo(tmp_path, "public/a")
    request = RouteRequest.create(
        tmp_path, paths=["public/b", "public/a", "public/b"]
    )
    result = resolve_scope(request, WorkBudget.start(5000))
    assert [candidate.id for candidate in result.selected] == [
        "public/a", "public/b",
    ]


def test_explicit_path_outside_root_is_rejected(tmp_path):
    outside = _repo(tmp_path.parent, "outside-route-repo")
    request = RouteRequest.create(tmp_path, paths=[str(outside)])
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.rejected[0]["reason_code"] == "outside-root"
    assert result.reconciliation["verdict"] == "MATCH"
    assert result.reconciliation["counts"] == {
        "candidates": 1,
        "selected": 0,
        "rejected": 1,
        "omitted": 0,
    }


def test_valid_workspace_map_seeds_candidates_without_global_scan(tmp_path):
    _repo(tmp_path, "public/index")
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": root_hash,
        "repositories": [{
            "path": "public/index",
            "class": "public",
            "markers": ["README.md"],
        }],
    }), encoding="utf-8")
    request = RouteRequest.create(tmp_path, query="index")
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.selected[0].source == "workspace-map"
    assert "query:index" in result.selected[0].signals
    assert result.complete is False
    assert result.source["validation"] == "UNVERIFIED"


def test_strict_mode_validates_map_against_repository_discovery(tmp_path):
    _repo(tmp_path, "public/index")
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": root_hash,
        "repositories": [{"path": "public/index"}],
    }), encoding="utf-8")
    request = RouteRequest.create(tmp_path, freshness="strict")
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.complete is True
    assert result.source["validation"] == "FRESH"


def test_query_scoring_uses_bounded_readme_title_and_matching_annotation(tmp_path):
    repo = _repo(tmp_path, "public/index")
    (repo / "README.md").write_text("# Evidence Router\n", encoding="utf-8")
    (tmp_path / ".index.toml").write_text(
        '[output.annotations]\n"public/index" = "bounded routing"\n',
        encoding="utf-8",
    )
    request = RouteRequest.create(tmp_path, query="evidence bounded")
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.selected[0].score == 2
    assert {"query:evidence", "query:bounded"} <= set(result.selected[0].signals)


def test_max_docs_zero_prevents_scope_readme_open(tmp_path):
    repo = _repo(tmp_path, "public/index")
    (repo / "README.md").write_text("# Evidence Router\n", encoding="utf-8")
    budget = WorkBudget.start(5000)
    request = RouteRequest.create(
        tmp_path, query="evidence", max_docs=0
    )
    result = resolve_scope(request, budget)
    assert result.selected[0].score == 0
    assert budget.counters["document_bodies_opened"] == 0


def test_max_repos_omits_with_receipts(tmp_path):
    for rel in ("public/a", "public/b", "public/c"):
        _repo(tmp_path, rel)
    request = RouteRequest.create(
        tmp_path,
        paths=["public/c", "public/b", "public/a"],
        max_repos=1,
    )
    budget = WorkBudget.start(5000)
    result = resolve_scope(request, budget)
    assert len(result.selected) == 1
    assert len(result.omitted) == 2
    assert {item["reason_code"] for item in result.omitted} == {"max-repos"}
    assert result.reconciliation["verdict"] == "MATCH"
    assert budget.counters["repositories_visited"] == 1
```

- [ ] **Step 2: Run RED**

Run:

```text
python -m pytest tests/test_route_scope.py -q
```

Expected: import fails for `index_graph.route.scope`.

- [ ] **Step 3: Implement candidate and result types**

Create `src/index_graph/route/scope.py` with:

```python
"""Task scope resolution: explicit paths, map hints, scoring, bounded discovery."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import load_config
from ..scan import discover_repos
from .budget import WorkBudget
from .model import RouteRequest, reconcile_route, route_item
from .reads import DocumentReader

_TOKEN = re.compile(r"[0-9a-z]+")


@dataclass(frozen=True)
class RepoCandidate:
    id: str
    path: Path | None
    rel_path: str
    source: str
    score: int = 0
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopeResult:
    candidates: tuple[RepoCandidate, ...]
    selected: tuple[RepoCandidate, ...]
    rejected: tuple[dict, ...]
    omitted: tuple[dict, ...]
    complete: bool
    source: dict
    reconciliation: dict
```

Implement helpers with these exact contracts:

```python
def _root_id(root: Path) -> str:
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]


def _candidate(root: Path, path: Path, source: str, metadata: dict | None = None):
    rel = path.relative_to(root).as_posix() or "."
    terms = {rel.lower(), path.name.lower()}
    if metadata:
        terms.add(str(metadata.get("class", "")).lower())
        terms.update(str(marker).lower() for marker in metadata.get("markers", ()))
        terms.update(str(term).lower() for term in metadata.get("annotations", ()))
        if metadata.get("readme_title"):
            terms.add(str(metadata["readme_title"]).lower())
    return RepoCandidate(rel, path, rel, source, signals=tuple(sorted(terms)))


def _score(candidate: RepoCandidate, query: str) -> RepoCandidate:
    tokens = set(_TOKEN.findall(query.lower()))
    matched = tuple(sorted(token for token in tokens if any(
        token in signal for signal in candidate.signals
    )))
    return RepoCandidate(
        candidate.id,
        candidate.path,
        candidate.rel_path,
        candidate.source,
        score=len(matched),
        signals=candidate.signals + tuple(f"query:{token}" for token in matched),
    )
```

Implement `resolve_scope` using the precedence from the specification:

1. normalize, deduplicate, and sort explicit inputs, or parse all
   root-matching map rows into cheap in-memory metadata, or perform
   checkpointed discovery with repository contents pruned;
2. compute the coarse score from portable path/name and already-present
   map/config metadata only; do not stat a repository or open a README yet;
3. sort by `(-coarse_score, id)`, form a shortlist of at most `max_repos`, and
   immediately reconcile all remaining known candidates as `max-repos`;
4. validate only shortlisted filesystem paths. Accept both relative and
   absolute explicit inputs but emit only root-relative IDs; `"."` selects a
   repository at the route root;
5. when a query is present, enrich only validated shortlisted candidates with
   the path-specific configured annotation and a README H1 obtained through
   the shared `DocumentReader`; `max_docs=0` therefore opens no README;
6. rescore/sort within the shortlist, never pulling an unvisited candidate
   across the declared repository-work boundary;
7. emit typed rejection/omission receipts, using a stable redacted identifier
   rather than echoing an absolute outside-root input;
8. call `reconcile_route`.

Before validating/enriching each shortlisted repository candidate, call
`budget.checkpoint("scope.repo", counter="repositories_visited")`; a failed
checkpoint stops new candidate work and leaves the scope incomplete.

Repository identity is the portable relative path, not a basename, so duplicate
repository names cannot collapse. Set `ScopeResult.complete=False` when a
checkpoint prevents discovery or scoring from completing, and include the
first exhaustion boundary in its omission evidence.

`ScopeResult.candidates` includes every observed input needed by the
reconciliation equation, including rejected explicit inputs. Represent a
rejected outside-root/not-found input as a `RepoCandidate` whose `path=None`
and whose `id` is either its safe normalized root-relative spelling or a
stable redacted digest such as `outside-root:<sha256-prefix>`. Only candidates
with a validated non-`None` path may enter `selected`. This keeps
`candidates = selected + rejected + omitted` closed without leaking absolute
external paths or inventing a usable filesystem location.

Populate `ScopeResult.source` with source kind, map path/age when applicable,
and validation state. A root-matching map is still only `UNVERIFIED` in
bounded mode because it cannot prove no repository was added after generation;
selected map paths are checked but the scope remains incomplete, so the route
cannot be `MATCH`. In strict mode, run checkpointed repository discovery and
compare the complete discovered set to the map. Mark it `FRESH` only when that
comparison finishes and matches; on drift, use the freshly discovered set and
record the map as `DRIFT`; on budget exhaustion, keep it `UNKNOWN` and the
scope incomplete.

- [ ] **Step 4: Run GREEN and commit**

Run:

```text
python -m pytest tests/test_route_scope.py tests/test_route_budget.py -q
git diff --check
```

Expected: all tests pass.

Commit:

```text
git add src/index_graph/route/scope.py tests/test_route_scope.py
git commit -m "feat(route): resolve bounded repository scope"
```

---

### Task 4: Scoped document selection with a real body-read cap

**Files:**
- Create: `src/index_graph/route/documents.py`
- Create: `tests/test_route_documents.py`

**Interfaces:**
- Produces `DocumentResult(docs, candidates, rejected, omitted, complete, reconciliation)`.
- Produces
  `select_documents(root, repositories, query, max_docs, budget, *, reader=None)`.
- Opens at most `max_docs` bodies and never walks outside selected repositories.

- [ ] **Step 1: Write failing document tests**

Create `tests/test_route_documents.py`:

```python
from index_graph.route.budget import WorkBudget
from index_graph.route.documents import select_documents
from index_graph.route.reads import DocumentReader
from index_graph.route.scope import RepoCandidate


def _candidate(root, rel):
    repo = root / rel
    (repo / ".git").mkdir(parents=True)
    return RepoCandidate(rel, repo, rel, "explicit")


def test_max_docs_caps_bodies_opened(tmp_path):
    candidate = _candidate(tmp_path, "public/index")
    for number in range(20):
        (candidate.path / f"doc-{number:02}.md").write_text(
            f"# Doc {number}\nbody\n", encoding="utf-8"
        )
    budget = WorkBudget.start(5000)
    result = select_documents(tmp_path, [candidate], "", 8, budget)
    assert len(result.docs) == 8
    assert budget.counters["document_bodies_opened"] == 8
    assert len(result.omitted) == 12
    assert {item["reason_code"] for item in result.omitted} == {"max-docs"}


def test_document_walk_never_visits_unselected_sibling(tmp_path):
    selected = _candidate(tmp_path, "public/index")
    sibling = _candidate(tmp_path, "public/forum")
    (selected.path / "README.md").write_text("# Index\n", encoding="utf-8")
    (sibling.path / "SECRET.md").write_text("# Must not be read\n", encoding="utf-8")
    result = select_documents(tmp_path, [selected], "index", 8, WorkBudget.start(5000))
    assert [doc.rel_path for doc in result.docs] == ["public/index/README.md"]


def test_budget_expiration_omits_remaining_documents(tmp_path):
    candidate = _candidate(tmp_path, "public/index")
    for number in range(5):
        (candidate.path / f"{number}.md").write_text("# D\n", encoding="utf-8")
    ticks = iter((0.0, 0.0, 0.003, 0.006, 0.006, 0.006, 0.006))
    budget = WorkBudget.start(5, clock=lambda: next(ticks, 0.006))
    result = select_documents(tmp_path, [candidate], "", 8, budget)
    assert result.complete is False
    assert any(item["reason_code"] == "budget-exhausted" for item in result.omitted)
```

- [ ] **Step 2: Run RED**

Run:

```text
python -m pytest tests/test_route_documents.py -q
```

Expected: import fails for `index_graph.route.documents`.

- [ ] **Step 3: Implement deterministic scoped document selection**

Create `src/index_graph/route/documents.py`. Use `EXCLUDE_DIRS`,
`knowledge.docs._parse_doc`, and the Task 1 `DocumentReader`. The
implementation must:

```python
@dataclass(frozen=True)
class DocumentResult:
    docs: tuple[Doc, ...]
    candidates: tuple[str, ...]
    rejected: tuple[dict, ...]
    omitted: tuple[dict, ...]
    complete: bool
    reconciliation: dict
```

Enumeration rules:

```python
for repository in sorted(repositories, key=lambda item: item.id):
    for dirpath, dirnames, filenames in os.walk(repository.path, onerror=...):
        if not budget.checkpoint(
            "docs.directory", counter="directories_visited"
        ):
            stop = True
            break
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDE_DIRS)
        for filename in sorted(filenames):
            if filename.lower().endswith((".md", ".markdown")):
                budget.counters["candidate_documents_observed"] += 1
                candidates.append(path.relative_to(root).as_posix())
```

Sort candidate paths by:

```python
def _rank(path: str, query: str) -> tuple:
    tokens = set(_TOKEN.findall(query.lower()))
    score = sum(token in path.lower() for token in tokens)
    readme = Path(path).name.lower() == "readme.md"
    return (-score, -int(readme), path)
```

Iterate every ranked observed candidate through the supplied shared
`DocumentReader` (or create one when omitted). The reader may return a body
already opened during scope scoring even after the cap is full; this prevents
cached lower-ranked READMEs from disappearing merely because earlier
candidates could not start. A failed reader call does not increment the
counter or open the file. Parse successful reads with `_parse_doc`; use
`reader.reason(path)` to distinguish unreadable rejection from `max-docs` or
`budget-exhausted` omission. Reconcile every observed candidate. If
enumeration itself stops early, set `complete=False` and record
`enumeration_complete=False` plus the exhaustion boundary separately; never
imply that the unseen subtree was part of the closed candidate set.

- [ ] **Step 4: Run GREEN and commit**

Run:

```text
python -m pytest tests/test_route_documents.py tests/test_atlas.py -q
git diff --check
```

Expected: all tests pass and atlas behavior is unchanged.

Commit:

```text
git add src/index_graph/route/documents.py tests/test_route_documents.py
git commit -m "feat(route): bound document reads"
```

---

### Task 5: Incremental freshness manifest and constant-work cache identity

**Files:**
- Create: `src/index_graph/route/freshness.py`
- Create: `src/index_graph/route/cache.py`
- Create: `tests/test_route_cache.py`

**Interfaces:**
- `build_manifest(root, repositories, budget, *, scope_snapshot: dict,
  strict: bool, document_bodies: Mapping[str, str] | None = None) -> dict`.
- `validate_manifest(root, manifest, budget, *, strict: bool) -> dict` with
  `FRESH`, `DRIFT`, or `UNKNOWN`.
- `cache_identity(root, request) -> str` performs no recursive I/O.
- `RouteCache.get(key) -> dict | None`,
  `put(key, *, payload, markdown, manifest) -> None`, and `clear_memory()`.

- [ ] **Step 1: Write failing cache and drift tests**

Create `tests/test_route_cache.py`:

```python
import json
import os

from index_graph.route.budget import WorkBudget
from index_graph.route.cache import RouteCache, cache_identity
from index_graph.route.freshness import build_manifest, validate_manifest
from index_graph.route.model import RouteRequest
from index_graph.route.scope import RepoCandidate


def _scope(root):
    repo = root / "public/index"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src/mod.py").write_text("x = 1\n", encoding="utf-8")
    return [RepoCandidate("public/index", repo, "public/index", "explicit")]


def _snapshot(kind="explicit", candidates=("public/index",), complete=True):
    return {
        "kind": kind,
        "candidate_ids": list(candidates),
        "complete": complete,
        "map": None,
    }


def test_cache_identity_does_not_walk_workspace(tmp_path, monkeypatch):
    request = RouteRequest.create(tmp_path, paths=["public/index"])
    monkeypatch.setattr(os, "walk", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("cache identity must not walk")
    ))
    assert cache_identity(tmp_path, request) == cache_identity(tmp_path, request)
    tighter = RouteRequest.create(
        tmp_path, paths=["public/index"], budget_ms=request.budget_ms - 1
    )
    assert cache_identity(tmp_path, request) != cache_identity(tmp_path, tighter)


def test_strict_manifest_detects_same_metadata_edit_and_nested_addition(tmp_path):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    file = scope[0].path / "src/mod.py"
    before = file.stat()
    file.write_text("y = 1\n", encoding="utf-8")
    os.utime(file, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    (scope[0].path / "src/new.py").write_text("y = 1\n", encoding="utf-8")
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_strict_manifest_detects_same_metadata_markdown_edit(tmp_path):
    scope = _scope(tmp_path)
    readme = scope[0].path / "README.md"
    readme.write_text("# Alpha\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
        document_bodies={"public/index/README.md": "# Alpha\n"},
    )
    before = readme.stat()
    readme.write_text("# Bravo\n", encoding="utf-8")
    os.utime(readme, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_manifest_validation_uses_stats_not_recursive_walk(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    monkeypatch.setattr(os, "walk", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("hot validation must not walk")
    ))
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=False
    )["status"] == "FRESH"


def test_workspace_derived_manifest_detects_new_sibling_repository(tmp_path):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(kind="discovery"),
        strict=True,
    )
    sibling = tmp_path / "public/forum"
    (sibling / ".git").mkdir(parents=True)
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_route_cache_ignores_corrupt_entry(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    key = "abc"
    cache.clear_memory()
    cache.path_for(key).parent.mkdir(parents=True)
    cache.path_for(key).write_bytes(b"{not-json")
    assert cache.get(key) is None


def test_route_cache_ignores_incompatible_nested_schema(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    key = "incompatible"
    cache.clear_memory()
    cache.path_for(key).parent.mkdir(parents=True)
    cache.path_for(key).write_text(json.dumps({
        "schema": "index.route-cache-entry/v1",
        "payload": {"schema": "index.route-receipt/v0"},
        "manifest": {"schema": "index.route-manifest/v1"},
        "markdown": "",
    }), encoding="utf-8")
    assert cache.get(key) is None
```

- [ ] **Step 2: Run RED**

Run:

```text
python -m pytest tests/test_route_cache.py -q
```

Expected: imports fail for route freshness and cache modules.

- [ ] **Step 3: Implement manifests**

Create `src/index_graph/route/freshness.py`:

```python
"""Scoped manifests with bounded metadata and strict content validation."""
from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path

from ..freshness.fingerprint import is_relevant_filename
from ..graph.walk import EXCLUDE_DIRS

MANIFEST_SCHEMA = "index.route-manifest/v1"


def _stat(path: Path, root: Path) -> dict:
    value = path.stat()
    return {
        "path": path.relative_to(root).as_posix(),
        "mtime_ns": value.st_mtime_ns,
        "size": value.st_size,
    }
```

`build_manifest` walks only selected repository roots, tracks every visited
directory, every resolver-relevant file, and every Markdown candidate path,
then sorts records by path. Graph inputs carry content digests in strict mode.
Markdown candidates carry path/stat evidence, while only the bodies already
opened through `DocumentReader` carry content digests. This preserves the
global `max_docs` body-open cap:

```python
{
    "schema": MANIFEST_SCHEMA,
    "complete": not budget.exhausted,
    "root_id": _root_id(root),
    "config_id": _config_identity(root),
    "scope_snapshot": scope_snapshot,
    "repositories": [candidate.id, ...],
    "directories": [...],
    "files": [...],
    "graph_signatures": {"repo-id": "sha256-or-null"},
    "markdown_paths_signature": "sha256-or-null",
    "document_digests": {"root/relative/doc.md": "sha256"},
    "strict_signature": "combined-evidence-sha256-or-null",
    "last_strict_verified_at": "unix-seconds-or-null",
}
```

`_config_identity` hashes the first active `.index.toml` / `.repomap.toml`
configuration file (or a no-config marker), so a changed routing configuration
cannot validate against an old cache entry.

With `strict=False` and an explicit scope, `validate_manifest` does not call
`os.walk`. It checks the root/config identity and stats stored entries in
order, returns `DRIFT` on missing or changed entries, `UNKNOWN` with exact
unchecked counts when the budget expires, and `FRESH` only after every entry
validates. Directory mtime validation detects nested additions and deletions.
Workspace-derived scopes additionally perform the candidate-universe check
below because selected-root stats cannot detect a new sibling.

Validate the cached candidate universe before selected-repository evidence:

- `kind="explicit"` needs no sibling discovery because the caller declared
  the entire scope;
- a workspace-map snapshot validates a SHA-256 map-file content identity (not
  just mtime/size), and any cached
  result that could be `MATCH` reruns checkpointed,
  repo-content-pruned discovery before returning `FRESH`;
- a discovery snapshot reruns the same bounded discovery and compares its
  complete sorted IDs to `scope_snapshot["candidate_ids"]`;
- an incomplete/expired universe check is `UNKNOWN`; an added, removed, or
  renamed repository is `DRIFT`.

Thus a new sibling can never preserve a cached workspace-derived `MATCH`.
A bounded map route that was already `PARTIAL` may reuse its prior `PARTIAL`
payload after map/selected-path validation, but is never upgraded.

With `strict=True`, both manifest construction and validation recursively
enumerate the selected repositories. For resolver inputs, use the same sorted
`(relative-path, content-digest)` fold as `freshness.repo_fingerprint` and
store per-repository `graph_signatures`. Fold sorted Markdown relative paths
(not every Markdown body) into `markdown_paths_signature`, which detects
nested additions/removals. Hash the at-most-`max_docs` bodies supplied in
`document_bodies` into `document_digests`; strict validation reopens exactly
those paths, with `docs.open` counters, and never unselected document bodies.
Combine these components into `strict_signature`. The operation is
cooperative with `WorkBudget`; an interrupted signature is
incomplete/`UNKNOWN`, never `FRESH`. Add regression assertions that each
complete `graph_signatures[repo]` equals the existing
`repo_fingerprint(repo)`, selected Markdown body drift is detected even with
restored metadata, and a new Markdown path moves the path signature without
opening its body.

- [ ] **Step 4: Implement constant-work route caching**

Create `src/index_graph/route/cache.py`:

```python
"""Memory and disk cache for receipt-backed routes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from time import time

from .. import __version__
from .freshness import MANIFEST_SCHEMA
from .model import ROUTE_SCHEMA

CACHE_SCHEMA = "index.route-cache-entry/v1"
_MEMORY: dict[str, dict] = {}


def cache_identity(root: Path, request) -> str:
    payload = {
        "tool_version": __version__,
        "route_schema": ROUTE_SCHEMA,
        "cache_schema": CACHE_SCHEMA,
        "root": str(root.resolve()),
        "query": request.query,
        "paths": list(request.paths),
        "max_repos": request.max_repos,
        "max_docs": request.max_docs,
        "budget_ms": request.budget_ms,
        "freshness": request.freshness,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class RouteCache:
    def __init__(self, directory: Path | None = None):
        base = os.environ.get("INDEX_ROUTE_CACHE_DIR")
        local = os.environ.get("LOCALAPPDATA")
        self.directory = directory or (
            Path(base) if base else
            Path(local) / "index_graph" / "route-cache" if local else
            Path.home() / ".cache" / "index_graph" / "route-cache"
        )

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> dict | None:
        if key in _MEMORY:
            return deepcopy(_MEMORY[key])
        try:
            entry = json.loads(self.path_for(key).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if entry.get("schema") != CACHE_SCHEMA:
            return None
        if entry.get("payload", {}).get("schema") != ROUTE_SCHEMA:
            return None
        if entry.get("manifest", {}).get("schema") != MANIFEST_SCHEMA:
            return None
        _MEMORY[key] = entry
        return deepcopy(entry)

    def put(self, key: str, *, payload: dict, markdown: str, manifest: dict) -> None:
        entry = {
            "schema": CACHE_SCHEMA,
            "created_at": time(),
            "payload": payload,
            "markdown": markdown,
            "manifest": manifest,
        }
        _MEMORY[key] = entry
        try:
            path = self.path_for(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(entry, separators=(",", ":")), encoding="utf-8"
            )
            temporary.replace(path)
        except OSError:
            pass

    @staticmethod
    def clear_memory() -> None:
        _MEMORY.clear()
```

Import `deepcopy` from `copy`, `ROUTE_SCHEMA` from `.model`, and
`MANIFEST_SCHEMA` from `.freshness`. The cache schema/version, tool version,
normalized root, and every normalized route argument (including
`budget_ms`) participate in identity. Cache reads return deep copies so a
caller cannot mutate the shared in-process entry. Cache writes use a sibling
temporary file plus `Path.replace` so interruption cannot leave a
half-written JSON entry.

- [ ] **Step 5: Run GREEN and commit**

Run:

```text
python -m pytest tests/test_route_cache.py tests/test_freshness.py tests/test_mcp.py -q
git diff --check
```

Expected: all tests pass.

Commit:

```text
git add src/index_graph/route/freshness.py src/index_graph/route/cache.py tests/test_route_cache.py
git commit -m "feat(route): add incremental freshness cache"
```

---

### Task 6: Shared route engine and deterministic Markdown adapter

**Files:**
- Create: `src/index_graph/route/engine.py`
- Modify: `src/index_graph/route/__init__.py`
- Modify: `src/index_graph/router.py`
- Create: `tests/test_route_engine.py`

**Interfaces:**
- Public `build_route(...) -> dict` has the exact specification signature.
- Internal
  `RouteEngine(cache=None, clock=time.monotonic, cache_enabled=True).build(request) -> dict`.
- `render_route_router(payload) -> str` excludes measured elapsed time.

- [ ] **Step 1: Write failing end-to-end engine tests**

Create `tests/test_route_engine.py`:

```python
import hashlib
import json

from index_graph.route import build_route
from index_graph.route.cache import RouteCache
from index_graph.route.engine import RouteEngine
from index_graph.route.model import RouteRequest
from index_graph.router import render_route_router


def _repo(root, rel):
    repo = root / rel
    (repo / ".git").mkdir(parents=True)
    (repo / "README.md").write_text(f"# {repo.name}\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        f"[project]\nname='{repo.name}'\nversion='0'\n", encoding="utf-8"
    )
    return repo


def _workspace_map(root, paths):
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    (root / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": digest,
        "repositories": [{"path": path} for path in paths],
    }), encoding="utf-8")


def test_explicit_route_is_complete_and_portable(tmp_path, monkeypatch):
    _repo(tmp_path, "public/index")
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    payload = build_route(tmp_path, paths=["public/index"], freshness="strict")
    assert payload["schema"] == "index.route-receipt/v1"
    assert payload["verdict"] == "MATCH"
    assert payload["selection"]["selected"] == ["public/index"]
    assert str(tmp_path) not in str(payload)
    assert payload["reconciliation"]["verdict"] == "MATCH"
    assert set(payload) == {
        "schema", "verdict", "root", "query", "freshness", "budget", "scope",
        "selection", "documents", "evidence", "reconciliation", "recheck",
    }


def test_limit_or_budget_omission_is_partial(tmp_path, monkeypatch):
    _repo(tmp_path, "public/a")
    _repo(tmp_path, "public/b")
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    payload = build_route(tmp_path, max_repos=1, freshness="strict")
    assert payload["verdict"] == "PARTIAL"
    assert payload["selection"]["omitted"][0]["reason_code"] == "max-repos"


def test_hot_cache_hit_does_not_rebuild_graph(tmp_path, monkeypatch):
    _repo(tmp_path, "public/index")
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    build_route(tmp_path, paths=["public/index"])
    import index_graph.route.engine as engine
    import index_graph.route.freshness as route_freshness
    import index_graph.freshness.fingerprint as fingerprint
    import index_graph.knowledge.docs as knowledge_docs

    def forbidden(name):
        return lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError(f"hot explicit hit must not call {name}")
        )

    monkeypatch.setattr(engine, "resolve_scope", forbidden("resolve_scope"))
    monkeypatch.setattr(engine, "select_documents", forbidden("select_documents"))
    monkeypatch.setattr(engine, "build_graph", forbidden("build_graph"))
    monkeypatch.setattr(route_freshness.os, "walk", forbidden("os.walk"))
    monkeypatch.setattr(fingerprint, "relevant_files", forbidden("relevant_files"))
    monkeypatch.setattr(knowledge_docs, "discover_docs", forbidden("discover_docs"))
    cached = build_route(tmp_path, paths=["public/index"])
    assert cached["freshness"]["validation"] == "FRESH"


def test_strict_workspace_cache_rebuilds_when_sibling_repo_is_added(
    tmp_path, monkeypatch
):
    _repo(tmp_path, "public/index")
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    first = build_route(tmp_path, freshness="strict")
    assert first["verdict"] == "MATCH"
    _repo(tmp_path, "public/forum")
    second = build_route(tmp_path, freshness="strict")
    assert second["verdict"] == "MATCH"
    assert second["selection"]["candidates"] == [
        "public/forum", "public/index",
    ]
    assert second["freshness"]["validation"] == "BUILT_AFTER_DRIFT"


def test_strict_map_cache_rebuilds_when_sibling_is_added(tmp_path, monkeypatch):
    _repo(tmp_path, "public/index")
    _workspace_map(tmp_path, ["public/index"])
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    assert build_route(tmp_path, freshness="strict")["verdict"] == "MATCH"
    _repo(tmp_path, "public/forum")
    rebuilt = build_route(tmp_path, freshness="strict")
    assert rebuilt["freshness"]["validation"] == "BUILT_AFTER_DRIFT"
    assert rebuilt["selection"]["candidates"] == [
        "public/forum", "public/index",
    ]


def test_strict_map_cache_rebuilds_when_map_file_changes(tmp_path, monkeypatch):
    _repo(tmp_path, "public/index")
    _workspace_map(tmp_path, ["public/index"])
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    assert build_route(tmp_path, freshness="strict")["verdict"] == "MATCH"
    _workspace_map(tmp_path, [])
    rebuilt = build_route(tmp_path, freshness="strict")
    assert rebuilt["freshness"]["validation"] == "BUILT_AFTER_DRIFT"
    assert rebuilt["verdict"] == "MATCH"


def test_cache_validation_timeout_is_stale_not_match(tmp_path, monkeypatch):
    _repo(tmp_path, "public/index")
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    request = RouteRequest.create(
        tmp_path, paths=["public/index"], budget_ms=5
    )
    RouteEngine(clock=lambda: 0.0).build(request)
    ticks = iter((0.0, 0.006))
    payload = RouteEngine(
        clock=lambda: next(ticks, 0.006)
    ).build(request)
    assert payload["verdict"] == "STALE"
    assert payload["freshness"]["validation"] == "UNKNOWN"
    assert payload["budget"]["exhausted_at"] == "freshness.root"


def test_missing_root_is_typed_unverifiable(tmp_path):
    payload = build_route(tmp_path / "missing", paths=["."])
    assert payload["verdict"] == "UNVERIFIABLE"
    assert payload["recheck"]


def test_markdown_is_deterministic_and_keeps_workspace_map(tmp_path, monkeypatch):
    _repo(tmp_path, "public/index")
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    payload = build_route(tmp_path, paths=["public/index"], freshness="strict")
    first = render_route_router(payload)
    second = render_route_router(payload)
    assert first == second
    assert "# Workspace map" in first
    assert "elapsed_ms" not in first
    assert "verdict=`MATCH`" in first
```

- [ ] **Step 2: Run RED**

Run:

```text
python -m pytest tests/test_route_engine.py -q
```

Expected: imports fail for `build_route` and `render_route_router`.

- [ ] **Step 3: Implement the orchestration flow**

Create `src/index_graph/route/engine.py` with:

```python
"""The one shared CLI/MCP/Python task-route engine."""
from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from time import monotonic
from typing import Literal

from ..graph.build import build_graph
from ..knowledge.atlas import build_router_pack
from ..router import render_route_router
from .budget import WorkBudget
from .cache import RouteCache, cache_identity
from .documents import select_documents
from .freshness import build_manifest, validate_manifest
from .model import ROUTE_SCHEMA, RouteRequest
from .scope import resolve_scope
```

Implement `RouteEngine.build` in this order:

1. create `WorkBudget`;
2. reject missing roots as `UNVERIFIABLE`;
3. compute constant-work cache identity and read the cache;
4. validate a cached manifest;
5. return a deep-copied cached payload as its original verdict when `FRESH`,
   replacing its freshness/cache-age and budget fields with facts from the
   current validation call;
6. return a deep-copied prior payload as `STALE` when validation is `UNKNOWN`,
   including exact checked/unchecked counts and the current exhaustion
   boundary;
7. rebuild on `DRIFT` or cache miss;
8. create one `DocumentReader`;
9. resolve scope with that reader, then select documents through the same
   reader so README query enrichment consumes the same global `max_docs` cap;
10. call `build_graph` with a wrapper that maps `graph.repo` to
    `repositories_visited`, graph walk directories to `directories_visited`,
    and all other boundaries to an uncounted `budget.checkpoint`; pass the same
    `DocumentReader.read` as `document_reader` so graph descriptions cannot
    bypass `max_docs`;
11. build the router pack and receipt;
12. build a bounded or strict manifest according to the requested freshness,
    passing `document_bodies=reader.bodies()` and a portable scope snapshot
    containing source kind, all candidate IDs, completeness, and map identity,
    so cold construction never reopens a document and future cache validation
    can detect sibling-repository drift;
13. only then derive `MATCH` versus `PARTIAL` from scope, document, graph,
    reconciliation, and manifest completeness;
14. render deterministic Markdown and cache the receipt only when it contains
    a usable selected route. An incomplete manifest remains explicitly
    incomplete and can never validate as `FRESH`.

The receipt contains every field required by the specification. Set:

```python
"selection": {
    "candidates": [candidate.id for candidate in scope.candidates],
    "selected": [candidate.id for candidate in scope.selected],
    "rejected": list(scope.rejected),
    "omitted": list(scope.omitted),
}
```

Use root-relative repository IDs as graph keys:

```python
repo_paths = {candidate.id: candidate.path for candidate in scope.selected}
repo_dirs = {candidate.id: candidate.rel_path for candidate in scope.selected}
```

Set top-level `root` to `"."`, never the absolute filesystem root. Populate
all twelve required top-level receipt fields. `freshness` must include
`mode`, `validation`, `cache_age_ms`, `source_signature`, and
`recursive_complete`; `scope` must include the declared controls and
completion flags; `documents` must contain selected, rejected, omitted, and
reconciliation data; and `recheck` must contain portable CLI/MCP commands.

The final verdict rules are closed:

- `UNVERIFIABLE` when the root is missing/unreadable or no usable selected
  repository can be established;
- `STALE` only when a prior usable receipt is returned but current cache
  validation is incomplete;
- `PARTIAL` when current work yields a usable route but any declared limit,
  checkpoint, graph warning, document traversal, manifest, or reconciliation
  is incomplete;
- `MATCH` only when every one of those components is complete and verified.

`RouteEngine(cache_enabled=False)` skips both cache lookup and cache write.
No wall-clock timing test uses real sleeps or a 1 ms race; inject the monotonic
clock as shown above.

Expose:

```python
def build_route(
    root: Path,
    *,
    query: str = "",
    paths: Sequence[str] = (),
    max_repos: int = 12,
    max_docs: int = 8,
    budget_ms: int = 5000,
    freshness: Literal["bounded", "strict"] = "bounded",
) -> dict:
    request = RouteRequest.create(
        root,
        query=query,
        paths=paths,
        max_repos=max_repos,
        max_docs=max_docs,
        budget_ms=budget_ms,
        freshness=freshness,
    )
    return RouteEngine().build(request)
```

- [ ] **Step 4: Implement deterministic Markdown**

In `src/index_graph/router.py`, add:

```python
def render_route_router(payload: dict) -> str:
    budget = payload.get("budget", {})
    selection = payload.get("selection", {})
    preamble = [
        "> Index route receipt: "
        f"verdict=`{payload.get('verdict')}` "
        f"freshness=`{payload.get('freshness', {}).get('validation', 'UNKNOWN')}` "
        f"budget_ms=`{budget.get('requested_ms')}` "
        f"repos=`{len(selection.get('selected', []))}` "
        f"omitted=`{len(selection.get('omitted', []))}` "
        f"directories=`{budget.get('directories_visited', 0)}` "
        f"documents_opened=`{budget.get('document_bodies_opened', 0)}` "
        f"files_validated=`{budget.get('files_validated', 0)}` "
        f"stopped_at=`{budget.get('exhausted_at')}`",
        "",
    ]
    workspace = render_router(
        payload.get("evidence", {}).get("router_pack", {}),
        max_docs=payload.get("scope", {}).get("max_docs", 8),
    )
    return "\n".join(preamble) + workspace
```

Do not include `elapsed_ms` in Markdown.
If no router pack exists (for example an `UNVERIFIABLE` receipt), return the
receipt preamble plus the portable rejection/recheck summary instead of
calling `render_router` with an invalid empty pack.

Update `src/index_graph/route/__init__.py` to export `build_route`.

- [ ] **Step 5: Run GREEN, renderer regression tests, and commit**

Run:

```text
python -m pytest tests/test_route_engine.py tests/test_router.py tests/test_router_deep_dives.py -q
git diff --check
```

Expected: all tests pass.

Commit:

```text
git add src/index_graph/route/engine.py src/index_graph/route/__init__.py src/index_graph/router.py tests/test_route_engine.py
git commit -m "feat(route): build receipt-backed task routes"
```

---

### Task 7: CLI route and route-backed router

**Files:**
- Create: `src/index_graph/cli_handlers/route.py`
- Modify: `src/index_graph/cli_handlers/__init__.py`
- Modify: `src/index_graph/cli_parser.py`
- Modify: `src/index_graph/cli.py`
- Create: `tests/test_route_cli.py`
- Modify: `tests/test_router.py`

**Interfaces:**
- `index route` emits JSON with `--json`, otherwise a concise verdict and selected paths.
- `index router` accepts the same route controls and renders route-backed Markdown.
- Existing `index router --no-cache` remains accepted and bypasses route-cache
  reads/writes; `index route` intentionally has no `--no-cache` flag.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_route_cli.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path


def _run(args, cache):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    env["INDEX_ROUTE_CACHE_DIR"] = str(cache)
    return subprocess.run(
        [sys.executable, "-m", "index_graph", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _repo(root):
    repo = root / "public/index"
    (repo / ".git").mkdir(parents=True)
    (repo / "README.md").write_text("# Index\n", encoding="utf-8")
    return repo


def test_route_cli_json_and_defaults(tmp_path):
    _repo(tmp_path)
    result = _run(
        ["route", "--root", str(tmp_path), "--path", "public/index", "--json"],
        tmp_path / "cache",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "index.route-receipt/v1"
    assert payload["scope"]["max_repos"] == 12
    assert payload["scope"]["max_docs"] == 8
    assert payload["budget"]["requested_ms"] == 5000


def test_route_cli_json_matches_python_semantics(tmp_path, monkeypatch):
    from index_graph.route import build_route
    from index_graph.route.cache import RouteCache

    _repo(tmp_path)
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "python-cache"))
    expected = build_route(tmp_path, paths=["public/index"])
    RouteCache.clear_memory()
    result = _run(
        ["route", "--root", str(tmp_path), "--path", "public/index", "--json"],
        tmp_path / "cli-cache",
    )
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    for payload in (expected, actual):
        payload["budget"].pop("elapsed_ms", None)
        payload["freshness"].pop("cache_age_ms", None)
    assert actual == expected


def test_router_cli_is_bounded_by_default(tmp_path):
    _repo(tmp_path)
    result = _run(
        ["router", "--root", str(tmp_path), "--max-docs", "1"],
        tmp_path / "cache",
    )
    assert result.returncode == 0, result.stderr
    assert "Index route receipt" in result.stdout
    assert "# Workspace map" in result.stdout


def test_cli_rejects_invalid_budget_before_work(tmp_path):
    result = _run(
        ["route", "--root", str(tmp_path), "--budget-ms", "0", "--json"],
        tmp_path / "cache",
    )
    assert result.returncode != 0
    assert "budget-ms" in (result.stdout + result.stderr)
```

- [ ] **Step 2: Run RED**

Run:

```text
python -m pytest tests/test_route_cli.py -q
```

Expected: CLI treats `route` as the default map invocation or rejects it.

- [ ] **Step 3: Add shared parser controls**

In `src/index_graph/cli_parser.py`, create:

```python
def _add_route_controls(parser, *, router: bool = False) -> None:
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--query", default="")
    parser.add_argument("--path", dest="paths", action="append", default=[])
    parser.add_argument("--max-repos", type=_nonnegative_int, default=12)
    parser.add_argument("--max-docs", type=_nonnegative_int, default=8)
    parser.add_argument("--budget-ms", type=_positive_int, default=5000)
    parser.add_argument(
        "--freshness", choices=("bounded", "strict"), default="bounded"
    )
    if router:
        parser.add_argument("--out", default=None)
        parser.add_argument("--no-cache", action="store_true")
    else:
        parser.add_argument("--json", action="store_true")
```

Add `_add_route_parser(sub)` and update `_add_router_parser` to use the shared
controls. Register `_add_route_parser(sub)` before `_add_router_parser(sub)`.
Implement `_positive_int` and `_nonnegative_int` as `argparse` type functions
that raise `argparse.ArgumentTypeError`; therefore an invalid control exits
before route work begins and names the hyphenated CLI option in the parser
error.

- [ ] **Step 4: Add handlers and dispatch**

Create `src/index_graph/cli_handlers/route.py` with:

```python
"""Task-route and route-backed workspace-router CLI handlers."""
from __future__ import annotations

import json
from pathlib import Path

from ..route.engine import RouteEngine
from ..route.model import RouteRequest
from ..router import render_route_router


def _payload(args):
    request = RouteRequest.create(
        args.root,
        query=args.query,
        paths=args.paths,
        max_repos=args.max_repos,
        max_docs=args.max_docs,
        budget_ms=args.budget_ms,
        freshness=args.freshness,
    )
    engine = RouteEngine(
        cache_enabled=not bool(getattr(args, "no_cache", False))
    )
    return engine.build(request)


def cmd_route(args) -> int:
    payload = _payload(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        selected = ", ".join(payload["selection"]["selected"]) or "(none)"
        print(f"route verdict={payload['verdict']} selected={selected}")
    return 1 if payload["verdict"] == "UNVERIFIABLE" else 0


def cmd_router(args) -> int:
    text = render_route_router(_payload(args))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0
```

Delete `cmd_router` and its now-unused router/cache imports from
`cli_handlers/maps.py`, move its export to this handler, and register `route`
in `_SUBCOMMANDS`, `_DISPATCH`, and handler exports. The exact `_payload`
implementation above makes `--no-cache` instantiate
`RouteEngine(cache_enabled=False)` without changing the public `build_route`
signature. Add a handler-level test with a fake cache whose `get` and `put`
raise if called, then assert `cmd_router` succeeds with `args.no_cache=True`.

- [ ] **Step 5: Run GREEN and commit**

Run:

```text
python -m pytest tests/test_route_cli.py tests/test_router.py tests/test_cli.py tests/test_cli_subcommands.py -q
python -m index_graph route --help
python -m index_graph router --help
git diff --check
```

Expected: selected tests pass; help shows all shared controls.

Commit:

```text
git add src/index_graph/cli.py src/index_graph/cli_parser.py src/index_graph/cli_handlers tests/test_route_cli.py tests/test_router.py
git commit -m "feat(route): expose bounded CLI routing"
```

---

### Task 8: MCP route, lazy workspace discovery, and parity

**Files:**
- Modify: `src/index_graph/mcp.py`
- Modify: `tests/test_mcp.py`

**Interfaces:**
- MCP advertises and serves `index.route`.
- `index_router` accepts route controls and calls the same engine.
- `_repo_paths(root)` is called only inside branches that need an exhaustive repository map.
- `index.map`, `index.invalidate`, route, wiki, symbols, status, and doctor do not pay an unused pre-scan.

- [ ] **Step 1: Write failing MCP and lazy-discovery tests**

Append to `tests/test_mcp.py`:

```python
def test_mcp_lists_task_route():
    response = handle_request({
        "jsonrpc": "2.0", "id": 80, "method": "tools/list"
    })
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    assert "index.route" in tools
    properties = tools["index.route"]["inputSchema"]["properties"]
    assert {"query", "paths", "max_repos", "max_docs", "budget_ms", "freshness"} <= set(properties)


def test_mcp_route_matches_python_payload(tmp_path, monkeypatch):
    from copy import deepcopy

    from index_graph.route import build_route
    from index_graph.route.cache import RouteCache

    repo = tmp_path / "public/index"
    (repo / ".git").mkdir(parents=True)
    (repo / "README.md").write_text("# Index\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "python-cache"))
    expected = build_route(tmp_path, paths=["public/index"])
    RouteCache.clear_memory()
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "mcp-cache"))
    response = handle_request({
        "jsonrpc": "2.0",
        "id": 81,
        "method": "tools/call",
        "params": {
            "name": "index.route",
            "arguments": {"root": str(tmp_path), "paths": ["public/index"]},
        },
    })
    assert response["result"]["isError"] is False
    actual = json.loads(response["result"]["content"][0]["text"])

    def stable(payload):
        payload = deepcopy(payload)
        payload["budget"].pop("elapsed_ms", None)
        payload["freshness"].pop("cache_age_ms", None)
        return payload

    assert stable(actual) == stable(expected)


def test_route_and_map_do_not_pay_unused_repo_prescan(tmp_path, monkeypatch):
    repo = tmp_path / "public/index"
    (repo / ".git").mkdir(parents=True)
    import index_graph.mcp as mcp_mod

    def forbidden(_root):
        raise AssertionError("unused _repo_paths pre-scan")

    monkeypatch.setattr(mcp_mod, "_repo_paths", forbidden)
    assert json.loads(mcp_mod.call_tool(
        "index.route", {"root": str(tmp_path), "paths": ["public/index"]}
    ))["schema"] == "index.route-receipt/v1"
    assert json.loads(mcp_mod.call_tool(
        "index.map", {"root": str(tmp_path)}
    ))["repo_count"] == 1


def test_mcp_router_default_is_receipt_backed(tmp_path, monkeypatch):
    repo = tmp_path / "public/index"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("INDEX_ROUTE_CACHE_DIR", str(tmp_path / "cache"))
    text = call_tool("index_router", {"root": str(tmp_path), "max_docs": 1})
    assert "Index route receipt" in text
    assert "# Workspace map" in text


def test_route_surfaces_bypass_legacy_recursive_cache_key(tmp_path, monkeypatch):
    repo = tmp_path / "public/index"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(
        "index_graph.mcp._workspace_signature",
        lambda _root: (_ for _ in ()).throw(
            AssertionError("route must not compute legacy workspace signature")
        ),
    )
    assert json.loads(call_tool(
        "index.route",
        {"root": str(tmp_path), "paths": ["public/index"]},
    ))["schema"] == "index.route-receipt/v1"
    assert "Index route receipt" in call_tool(
        "index_router",
        {"root": str(tmp_path), "paths": ["public/index"]},
    )
```

- [ ] **Step 2: Run RED**

Run:

```text
python -m pytest tests/test_mcp.py -q
```

Expected: `index.route` is unknown and `_repo_paths` is called before `index.map`.

- [ ] **Step 3: Register schemas and dispatch before global discovery**

In `src/index_graph/mcp.py`:

- add `"index.route"` to `_tool_defs()`;
- extend `index_router` with the same route properties;
- dispatch `index.route` and `index_router` immediately after confirming the
  root argument is present and resolving it, before generic directory
  validation and before `repo_paths = _repo_paths(root)`;
- return JSON for `index.route`;
- return `render_route_router(payload)` for `index_router`;
- move `repo_paths = _repo_paths(root)` down to the first graph/context branch;
- move `index.map` and `index.invalidate` above that assignment because they
  perform their own scoped work.

Use one argument adapter:

```python
def _route_arguments(args: dict) -> dict:
    return {
        "query": str(args.get("query", "")),
        "paths": tuple(args.get("paths") or ()),
        "max_repos": int(args.get("max_repos", 12)),
        "max_docs": int(args.get("max_docs", 8)),
        "budget_ms": int(args.get("budget_ms", 5000)),
        "freshness": str(args.get("freshness", "bounded")),
    }
```

The route engine, not MCP, owns semantic validation.

Concretely, keep the `"root" in args` requirement, resolve the supplied path,
then branch to `index.route` / `index_router` **before** the generic
`root.is_dir()` rejection so a missing route root becomes the engine's typed
`UNVERIFIABLE` receipt. All other tools retain their existing missing-root
error behavior. Remove `index_router` from `_CACHEABLE_TOOLS`; the shared route
cache is its only cache, so MCP must not compute `_workspace_signature` around
it. Do not add `index.route` to `_CACHEABLE_TOOLS`.

Move `index.map` and `index.invalidate` above
`repo_paths = _repo_paths(root)`. Their own implementations may still perform
the work inherent to those commands; this change removes only the currently
unused duplicate pre-scan. Keep context/graph/focus/verify/internals branches
below the lazy assignment because they consume the repository map.

- [ ] **Step 4: Run GREEN, stdio parity, and commit**

Run:

```text
python -m pytest tests/test_mcp.py tests/test_route_engine.py tests/test_route_cli.py -q
git diff --check
```

Expected: all selected tests pass.

Commit:

```text
git add src/index_graph/mcp.py tests/test_mcp.py
git commit -m "feat(route): expose bounded MCP routing"
```

---

### Task 9: Capability advertising, documentation, benchmark, and full gates

**Files:**
- Modify: `src/index_graph/flagship.py`
- Create: `src/index_graph/route/acceptance.py`
- Create: `scripts/benchmark_route.py`
- Create: `scripts/verify_route_acceptance.py`
- Modify: `tests/test_flagship_cli.py`
- Create: `tests/test_route_benchmark.py`
- Modify: `README.md`
- Modify: `USAGE.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Status advertises `route` and `index.route`.
- Doctor runs a bounded one-repository route probe.
- Benchmark emits one JSON object containing latency and work counters.
- Acceptance runner enforces a per-command wall timeout and writes captured
  route/router artifacts plus a JSON summary.

- [ ] **Step 1: Write failing capability and benchmark tests**

Add to `tests/test_flagship_cli.py`:

```python
def test_status_advertises_bounded_route():
    payload = status_payload()
    assert "route" in payload["native"]["commands"]
    assert "index.route" in payload["native"]["mcp_tools"]
    assert "bounded task routing" in payload["native"]["current_status"]


def test_doctor_checks_bounded_route():
    payload = doctor_payload()
    checks = {check["name"]: check for check in payload["native"]["checks"]}
    assert checks["mcp_route_probe"]["status"] == "MATCH"
    assert checks["mcp_route_probe"]["budget_ms"] == 5000
```

Create `tests/test_route_benchmark.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path


def test_route_benchmark_emits_machine_readable_work_receipt(tmp_path):
    repo = tmp_path / "public/index"
    (repo / ".git").mkdir(parents=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_route.py",
            "--root", str(tmp_path),
            "--path", "public/index",
            "--budget-ms", "5000",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "index.route-benchmark/v1"
    assert payload["route"]["schema"] == "index.route-receipt/v1"
    assert payload["elapsed_ms"] >= 0


def test_acceptance_runner_enforces_seven_second_deadline(tmp_path):
    repo = tmp_path / "public/index"
    (repo / ".git").mkdir(parents=True)
    (repo / "README.md").write_text("# Index\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_route_acceptance.py",
            "--root", str(tmp_path),
            "--path", "public/index",
            "--timeout-seconds", "7",
            "--out-dir", str(tmp_path / "receipts"),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "index.route-acceptance/v1"
    assert {check["status"] for check in payload["checks"]} == {"COMPLETED"}
    assert all(check["elapsed_ms"] <= 7000 for check in payload["checks"])


def test_acceptance_helper_preserves_timeout_artifacts(tmp_path):
    from subprocess import TimeoutExpired

    from index_graph.route.acceptance import run_command

    def timed_out(command, **_kwargs):
        raise TimeoutExpired(command, 7, output="partial stdout", stderr="partial stderr")

    check = run_command(
        "route", ["index", "route"], tmp_path, 7,
        runner=timed_out, clock=iter((0.0, 7.0)).__next__,
    )
    assert check["status"] == "TIMEOUT"
    assert (tmp_path / "route.stdout.txt").read_text(encoding="utf-8") == "partial stdout"
    assert (tmp_path / "route.stderr.txt").read_text(encoding="utf-8") == "partial stderr"


def test_acceptance_helper_rejects_over_limit_success(tmp_path):
    from subprocess import CompletedProcess

    from index_graph.route.acceptance import run_command

    check = run_command(
        "router", ["index", "router"], tmp_path, 7,
        runner=lambda command, **_kwargs: CompletedProcess(command, 0, "out", "err"),
        clock=iter((0.0, 7.001)).__next__,
    )
    assert check["status"] == "OVER_LIMIT"
    assert check["exit_code"] == 0
    assert (tmp_path / "router.stdout.txt").read_text(encoding="utf-8") == "out"
    assert (tmp_path / "router.stderr.txt").read_text(encoding="utf-8") == "err"
```

- [ ] **Step 2: Run RED**

Run:

```text
python -m pytest tests/test_flagship_cli.py tests/test_route_benchmark.py -q
```

Expected: route is absent from status/doctor and both route scripts are missing.

- [ ] **Step 3: Advertise and probe the route**

In `src/index_graph/flagship.py`:

- add `"route"` to `native.commands`;
- add `"index.route"` to `native.mcp_tools`;
- update `current_status` to include `bounded task routing`;
- add `_mcp_route_probe()` modeled on `_mcp_map_probe()`, using one temporary
  repository and arguments `paths=["solo"]`, `budget_ms=5000`;
- include `budget_ms`, `elapsed_ms`, verdict, and selected count in the check;
- add the check to `doctor_payload()`.

- [ ] **Step 4: Add the non-gating benchmark**

Create `scripts/benchmark_route.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from index_graph.route import build_route


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--path", dest="paths", action="append", default=[])
    parser.add_argument("--query", default="")
    parser.add_argument("--budget-ms", type=int, default=5000)
    args = parser.parse_args()
    start = perf_counter()
    route = build_route(
        args.root,
        query=args.query,
        paths=args.paths,
        budget_ms=args.budget_ms,
    )
    elapsed = round((perf_counter() - start) * 1000, 3)
    print(json.dumps({
        "schema": "index.route-benchmark/v1",
        "elapsed_ms": elapsed,
        "route": route,
    }, indent=2, sort_keys=True))
    return 1 if route["verdict"] == "UNVERIFIABLE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Add the hard-timeout acceptance runner**

Create `src/index_graph/route/acceptance.py` with:

```python
def run_command(label, command, out_dir, timeout_seconds, *, runner=subprocess.run,
                clock=perf_counter) -> dict:
```

The helper creates `out_dir`, executes the supplied command with
`timeout=timeout_seconds`, `capture_output=True`, and `text=True`, always
writes `{label}.stdout.txt` / `{label}.stderr.txt`, and returns a typed check.
`TimeoutExpired` becomes `status="TIMEOUT"` with preserved partial output;
a normal process is `COMPLETED` only if its exit code is zero and elapsed time
is within the limit; a zero-exit process over the measured limit is
`OVER_LIMIT`; other exits are `FAILED`. Injected `runner` and `clock` make all
four paths deterministic unit tests.

Create `scripts/verify_route_acceptance.py` as a thin argparse wrapper around
that helper. Parse `--root`, repeatable `--path`, `--timeout-seconds`
(default `7`), and required `--out-dir`. Pass these two child commands to
`run_command`:

```text
python -m index_graph route --root ROOT --path PATH --budget-ms 5000 --json
python -m index_graph router --root ROOT --max-docs 8 --budget-ms 5000
```

Print one `index.route-acceptance/v1` JSON summary containing command, status,
exit code, elapsed milliseconds, artifact paths, and parsed route
verdict/counts where available. Exit nonzero if either check is not
`COMPLETED`. The script never imports or invokes WSL.

- [ ] **Step 6: Update public documentation**

Update `README.md` command synopsis and quickstart with:

```text
index route --root . --query "repair CI" --budget-ms 5000 --json
index route --root . --path public/index --json
index router --root . --max-docs 8 --freshness bounded
```

Document that bounded routing may return `PARTIAL` or `STALE`, and that
`--freshness strict` performs complete nested-edit verification.

Add a complete `index route` section to `USAGE.md` covering:

- precedence of explicit paths, map hints, query scoring, and discovery;
- all defaults and verdicts;
- cache validation;
- deterministic Markdown versus structured elapsed timing;
- `index router --no-cache` (and explicitly note that `index route` has no
  corresponding flag);
- troubleshooting a `PARTIAL`, `STALE`, or `UNVERIFIABLE` result.

Add a top `CHANGELOG.md` entry naming:

- the observed 300-second MCP timeout and approximately 516-second return;
- the July 15 nested-edit correctness fix;
- constant-work route-cache identity;
- bounded discovery and document reads;
- new CLI/MCP/Python surfaces;
- no weakening of strict freshness.

- [ ] **Step 7: Run targeted GREEN and commit**

Run:

```text
python -m pytest tests/test_flagship_cli.py tests/test_route_benchmark.py -q
$env:PYTHONPATH = "$(Resolve-Path src);C:/dev/public/public-surface-sweeper/src"
python -m public_surface_sweeper . --json --fail-on error
git diff --check
```

Expected: tests pass; the separately checked-out sweeper has no error-severity
route-documentation defect. If
`C:/dev/public/public-surface-sweeper/src` is absent, record that exact external
tooling blocker and run the repository's own documentation tests; do not claim
the sweeper gate passed.

Commit:

```text
git add src/index_graph/flagship.py src/index_graph/route/acceptance.py scripts/benchmark_route.py scripts/verify_route_acceptance.py tests/test_flagship_cli.py tests/test_route_benchmark.py README.md USAGE.md CHANGELOG.md
git commit -m "docs(route): ship bounded routing surface"
```

- [ ] **Step 8: Run the complete local verification gate**

Run from the isolated worktree:

```text
python -m pytest
python -m index_graph status --json
python -m index_graph doctor --json
python -m index_graph route --root . --path . --freshness strict --json
python scripts/benchmark_route.py --root . --path . --budget-ms 5000
git diff --check
git status --short --branch
```

Expected:

- full pytest exits `0`;
- status advertises `route` and `index.route`;
- doctor reports `MATCH`, including `mcp_route_probe`;
- strict single-repository route returns a reconciled receipt;
- benchmark returns `index.route-benchmark/v1`;
- no whitespace errors;
- only intentional branch commits are present.

Before these commands, restore the worktree source path if the sweeper command
changed it:

```text
$env:PYTHONPATH = "$(Resolve-Path src)"
python -c "import index_graph, pathlib; print(pathlib.Path(index_graph.__file__).resolve())"
```

- [ ] **Step 9: Run the controlled workspace acceptance gates**

Do not invoke WSL. Run the hard-timeout wrapper:

```text
$env:PYTHONPATH = "$(Resolve-Path src)"
python scripts/verify_route_acceptance.py --root C:/dev --path public/index --timeout-seconds 7 --out-dir C:/dev/scratch/index-router-wave2-2026-07-18/acceptance
```

Expected:

- the wrapper exits `0`, both child checks are `COMPLETED`, and each measured
  `elapsed_ms <= 7000`;
- explicit-path route selects only
  `public/index`;
- formerly wedged router returns a receipt-backed `MATCH`, `PARTIAL`, or
  `STALE` result before the host timeout;
- neither output claims complete evidence when work was omitted;
- no WSL process or service is started.

Copy the wrapper's measured command, exit code, elapsed time, verdict,
selected count, omission count, and artifact paths into
`C:/dev/scratch/index-router-wave2-2026-07-18/VERIFICATION.md`.

---

## Final Review and Publication Gate

After all task commits:

1. Generate a full branch review package from merge base `origin/main`.
2. Dispatch an independent whole-branch reviewer against the approved
   specification and this plan.
3. Fix every Critical or Important finding and rerun its covering tests.
4. Rerun the complete local gate and controlled workspace acceptance gates.
5. Commit only verified fixes.
6. Push `agent/index-router-performance`.
7. Open a ready-for-review PR with root cause, behavior contract, benchmarks,
   exact tests, and compatibility notes.
8. Wait for GitHub Actions; address failures through exact log evidence.
9. Merge only when required checks are green and review findings are closed.
10. Recheck the default-branch workflow and add PR, merge SHA, and run URLs to
    the durable verification ledger.
