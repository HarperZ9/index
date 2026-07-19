# Bounded Task Routing and Incremental Freshness

Date: 2026-07-18
Status: approved for specification
Target: Index CLI, MCP, and Python API

## Problem

`index_router(root="C:/dev", max_docs=8)` exceeded the MCP tool's
300-second timeout and returned only after approximately 516 seconds. The
output limit did not constrain the work performed.

The slowdown is a consequence of three unbounded workspace passes:

1. `call_tool()` discovers every repository before consulting the cache.
2. The MCP cache key recursively stats every graph-relevant file before every
   cache lookup.
3. Router construction discovers and reads every Markdown document, then
   applies `max_docs` only while rendering.

The recursive cache signature was introduced on 2026-07-15 to fix a real
correctness defect: the prior top-level signature could serve a stale map
after a nested source edit or addition. This design must preserve that
freshness guarantee in strict mode. Reverting to a cheap but misleading cache
is not acceptable.

Index also lacks a task-altitude route surface. A caller that already knows
the task, repository paths, or recovery checkpoint can request only a complete
workspace router. That forces inventory work where focused routing would be
both more useful and substantially cheaper.

## Goals

- Make task routing bounded by default and prevent workspace-wide MCP calls
  from wedging their host.
- Add a deterministic, evidence-backed `index route` surface for task-focused
  repository and document selection.
- Let explicit paths bypass unrelated workspace discovery.
- Make limits constrain filesystem work, not only output rendering.
- Preserve strict nested-edit and nested-add freshness verification.
- Never label cached, partial, stale, or unverified evidence as current.
- Keep CLI, MCP, and Python behavior aligned.
- Preserve deterministic ordering and portable output.

## Non-goals

- Semantic embeddings, model calls, or probabilistic repository selection.
- A daemon, background service, or mandatory filesystem watcher.
- Replacing `index map`, the complete atlas, or strict workspace
  certification.
- Treating an old `WORKSPACE-REPO-MAP.json` as current without validation.
- Hiding omitted work or silently returning stale evidence.

## Design Invariants

1. Every route reconciles candidates into selected, rejected, and omitted
   sets.
2. A budget expiration produces a typed result, not a process hang.
3. `MATCH` requires complete, verified evidence for the declared scope.
4. A cached result that cannot be fully revalidated is `STALE`, never
   `MATCH`.
5. `strict` freshness detects nested edits and nested additions exactly as the
   current recursive signature does.
6. Explicit paths are contained by `root`; traversal outside `root` is
   rejected.
7. `max_docs` is an upper bound on document bodies opened by the route.
8. Portable output contains root-relative paths only.
9. CLI, MCP, and Python share one route engine and one receipt schema.

## Public Surface

### CLI

```text
index route --root ROOT \
  [--query TEXT] \
  [--path RELATIVE_PATH]... \
  [--max-repos 12] \
  [--max-docs 8] \
  [--budget-ms 5000] \
  [--freshness bounded|strict] \
  [--json]
```

Defaults:

- `max_repos = 12`
- `max_docs = 8`
- `budget_ms = 5000`
- `freshness = bounded`

`--path` is repeatable. Explicit paths take precedence over query-derived
candidates.

### MCP

Add `index.route` with the same arguments and defaults:

```json
{
  "root": "C:/dev",
  "query": "repair the Index router timeout",
  "paths": ["public/index"],
  "max_repos": 12,
  "max_docs": 8,
  "budget_ms": 5000,
  "freshness": "bounded"
}
```

Extend the existing `index_router` schema with `paths`, `max_repos`,
`budget_ms`, and `freshness`. Its existing `root` and `max_docs` arguments
remain valid. The default call becomes bounded so the exact call that wedged
the host cannot perform unlimited work.

### Python

Expose one shared entry point:

```python
build_route(
    root: Path,
    *,
    query: str = "",
    paths: Sequence[str] = (),
    max_repos: int = 12,
    max_docs: int = 8,
    budget_ms: int = 5000,
    freshness: Literal["bounded", "strict"] = "bounded",
) -> dict
```

CLI and MCP handlers only validate transport arguments and serialize this
result.

## Receipt

`index route --json` and `index.route` return
`index.route-receipt/v1`.

Required top-level fields:

```text
schema
verdict
root
query
freshness
budget
scope
selection
documents
evidence
reconciliation
recheck
```

### Verdicts

- `MATCH`: the declared scope was completely evaluated and all returned
  evidence was verified.
- `PARTIAL`: a declared limit or work budget omitted candidates, repositories,
  documents, or validation work.
- `STALE`: a prior verified snapshot was returned but could not be completely
  revalidated within the current call.
- `UNVERIFIABLE`: no usable route could be established.

`freshness` records the requested mode, cache age, validation state, source
snapshot signature, and whether recursive validation completed.

`budget` records requested milliseconds, elapsed milliseconds, repositories
visited, directories visited, candidate documents observed, document bodies
opened, and the boundary at which work stopped.

`reconciliation` proves:

```text
candidates = selected + rejected + omitted
```

Each rejected or omitted item carries a stable reason code.

## Architecture

### 1. Work Budget

A monotonic `WorkBudget` is created at the public API boundary. It owns:

- the deadline;
- deterministic counters;
- a `checkpoint(boundary)` method;
- the first exhaustion boundary.

Repository discovery, manifest validation, document enumeration, document
opening, graph construction, and cache validation call `checkpoint()` at
bounded units of work. No worker thread is abandoned and no asynchronous
exception is injected. Once exhausted, the engine stops starting new units
and reconciles the work already observed.

Strict mode still accepts a budget argument for observability but does not
claim a complete result when that budget expires.

### 2. Scope Resolution

Scope resolution uses this precedence:

1. validated explicit paths;
2. a validated repository snapshot or workspace map;
3. deterministic query scoring over known repository metadata;
4. bounded filesystem discovery.

Explicit paths are resolved beneath `root`, deduplicated, and sorted. A path
that escapes the root, does not exist, or is not a repository receives a typed
rejection.

Query scoring is deterministic and local. It uses repository name and path,
classification, marker filenames, README title, and configured annotations.
It does not invoke a model or embeddings. Every score component is included
as evidence.

An existing `WORKSPACE-REPO-MAP.json` may seed candidates only when its root
identity matches. Its age and validation state are recorded. A stale map is a
hint whose selected paths must be checked; it is never proof that the
workspace is current.

### 3. Document Selection

The route enumerates document names only inside selected repository scopes.
Paths are sorted before selection. Query and repository evidence rank
candidate paths without opening document bodies.

At most `max_docs` document bodies are opened. Parsing titles and wiki links
therefore cannot exceed the caller's declared read budget. Remaining
candidates are reconciled as omitted with `max-docs`.

The complete atlas may continue using exhaustive document discovery. The new
bounded route must not call exhaustive `discover_docs(root)`.

### 4. Cache and Incremental Freshness

Cache identity is computed in constant work from:

- tool and schema version;
- normalized root;
- normalized route arguments;
- configured freshness mode.

It does not recursively scan the workspace before lookup.

Each cache entry stores:

- the route receipt and rendered router text;
- creation time and last strict-verification time;
- the strict content signature, when available;
- selected repository paths;
- tracked relevant-file metadata;
- tracked directory metadata needed to detect additions;
- completeness and exhaustion information.

Bounded validation spends only the current budget:

1. validate root and configuration identity;
2. validate explicit or selected repository roots;
3. validate tracked file and directory metadata until the budget is exhausted;
4. return `MATCH` only if validation completes;
5. otherwise return the prior receipt as `STALE`, with exact unchecked scope.

Strict validation performs the current recursive relevant-file signature and
detects both nested content edits and new relevant files. A changed signature
invalidates the entry and rebuilds it.

A hot in-process cache hit for an unchanged explicit scope must not invoke
workspace repository discovery, `relevant_files(root)`, exhaustive document
discovery, or graph construction.

### 5. Router Compatibility

`index_router` remains a Markdown tool. It uses the shared route engine and
includes a deterministic receipt preamble naming verdict, scope, freshness,
the declared budget, work counters, and omissions. Measured elapsed time
remains in the structured JSON receipt as a diagnostic and is not embedded in
the deterministic Markdown.

Existing repository, dependency, documentation, and deep-dive sections remain
stable when strict mode completes. Bounded output may omit sections only when
the receipt explicitly records the omission.

The CLI `index router` and MCP `index_router` accept the same routing and
freshness controls. The Python renderer consumes the same receipt.

## Error Handling

- Invalid numeric limits return typed argument errors before filesystem work.
- Missing roots return `UNVERIFIABLE`.
- Escaping paths are rejected with `outside-root`.
- Unreadable directories are recorded as rejected or omitted evidence.
- Expired budgets return `PARTIAL` or `STALE`, never a transport timeout.
- A corrupt cache entry is ignored and rebuilt within budget.
- An incompatible cache schema is ignored.
- Strict validation failure returns `UNVERIFIABLE` unless a prior snapshot is
  available, in which case it returns `STALE`.

## Verification Strategy

### Behavioral tests

- Explicit paths avoid global repository discovery.
- Paths outside the root are rejected.
- Query scoring is deterministic and evidence-carrying.
- Candidate reconciliation is exact.
- `max_repos` limits visited repositories.
- `max_docs` limits document-body opens.
- A budget expiration yields `PARTIAL` with the correct exhaustion boundary.
- A prior snapshot with incomplete validation yields `STALE`.
- Strict mode invalidates on a nested edit.
- Strict mode invalidates on a nested addition.
- CLI, MCP, and Python payloads agree.
- Portable output contains no absolute paths.
- Legacy router sections remain present after a complete strict build.

### Performance tests

Use instrumented filesystem adapters and a fake monotonic clock as the primary
CI proof. Tests assert work counts rather than fragile wall-clock speed.

- A hot explicit-scope cache hit performs no recursive walk, exhaustive
  document discovery, or graph rebuild.
- A bounded cold call stops at the injected deadline and reconciles all
  observed candidates.
- `max_docs=8` opens no more than eight document bodies regardless of fixture
  size.
- An explicit one-repository scope never visits sibling repositories.

Maintain a non-gating benchmark command for observed latency. On the local
workspace, the acceptance run is:

```text
index route --root C:/dev --path public/index --budget-ms 5000 --json
```

It must complete within seven seconds, report its measured work, and perform
no WSL operation.

The formerly wedged call is also rerun with the new defaults:

```text
index router --root C:/dev --max-docs 8
```

It must return a receipt-backed bounded result rather than exceed the MCP
timeout. A separate strict run is allowed to take longer but must remain
interruptible and honest about incomplete verification.

## Documentation and Release

Update:

- `README.md`
- `USAGE.md`
- `CHANGELOG.md`
- MCP tool descriptions and schemas
- status/doctor capability advertising
- examples for explicit-path and query-based routing

The release note must name the July 15 correctness/performance trade-off:
strict nested-change verification remains available, while task routing no
longer performs unlimited work before a cache lookup.

## Delivery Boundaries

This feature is one coherent implementation track:

1. receipt, budget, and scope primitives;
2. bounded document and repository selection;
3. incremental cache validation;
4. CLI/MCP/Python integration;
5. compatibility, documentation, and benchmarks.

No production publication occurs until the full Index test suite, status,
doctor, targeted performance gates, and independent code review pass.
