# Router jobs

`index_graph.router_jobs` is the durable local worker core for complete router
builds. The `index router-job` CLI and `index.router.job.*` MCP tools expose this
core through short start, status, result, cancel, and resume calls.

The problem it solves is host timeouts. A complete router build can take longer
than an interactive MCP call window on a large workspace. A caller needs to start
the full build quickly, poll real progress, retrieve only a complete result, and
recover safely if the host or worker is interrupted.

## Python core

```python
from pathlib import Path
from index_graph.router_jobs import (
    start_router_job,
    read_router_job_status,
    read_router_job_result,
    cancel_router_job,
    resume_router_job,
)

job = start_router_job(Path("/workspace"), max_docs=500)
status = read_router_job_status(job["job_id"])
result = read_router_job_result(job["job_id"])
```

A started job writes private local state under `INDEX_ROUTER_JOB_DIR` when that
environment variable is set. Otherwise it uses the platform user cache directory.
The state directory contains the request, status receipt, progress events, worker
logs, and the router output. These artifacts are local operational state and are
not public release artifacts.

## Status receipt

`status.json` uses `schema: index.router-job-status/v1` and records:

- `job_id`: opaque UUID job identifier.
- `tool_version` and `source_version`: the Index version that created the job.
- `status`: one of `running`, `cancellation_requested`, `complete`, `failed`,
  or `cancelled`.
- `phase`: current worker phase, including `queued`, `started`, `discovering`,
  `building`, `resolving`, `graph_complete`, `graph_failed`, `rendering`,
  `complete`, `failed`, or `cancelled`.
- `completed_repos` and `total_repos`: actual graph progress reported by
  `build_graph`; `total_repos` is `null` until discovery finishes.
- `phase_timings_ms`: private per-phase worker timings for local diagnosis,
  including router inventory, graph build, router-doc row construction, router
  pack assembly, rendering, and result publication when those phases have run.
- `router_inventory`: aggregate private traversal detail for the operation-local
  router inventory. It reports physical walk count, visited directory/file
  counts, metadata byte totals, discovered repo count, Markdown path count,
  graph file-list count, and per-repo inventory fallback count. These are
  traversal diagnostics, not source freshness. Reused graph file lists carry a
  directory-membership seal that is revalidated immediately before the graph
  fingerprint; changed, ambiguous, or unreadable membership falls back to the
  normal graph walk. Exact source-byte reads remain in `graph_cache.fingerprint`.
- `graph_cache`: aggregate private cache outcome counters and reason counts for
  the graph build. It reports hits, misses, invalid entries, bypassed entries,
  writes, cache-stage timings, and exact-byte fingerprint file/byte counts
  without file contents, source snippets, repo paths, or credentials.
- `router_docs`: aggregate private router-doc detail. It reports the inventory
  traversal timing used for Markdown path discovery and the row-construction
  timing used to build path-only doc records; it does not include Markdown
  bodies or paths.
- `attempt`, `run_token`, diagnostic `pid`, timestamps, and
  `result_available`.
- `request_sha256`, `config_sha256`, `result_sha256`, and `result_bytes` bind a
  complete result to the original request, local config snapshot, and final
  content.
- `error_type` and `message` for failed or cancelled jobs.

A partial or interrupted job never returns router markdown as a successful result.
`read_router_job_result()` returns an `index.router-job-result/v1` receipt with
`result_available: false` until `status` is `complete`, `request.json` still
matches `request_sha256`, and the canonical `router.md` regular file matches
`result_sha256`. Missing, tampered, symlinked, reparse-point, or non-regular
result files fail closed without returning content.

## Progress event scope

New `index.router-job-event/v1` rows in `events.jsonl` include `scope`,
`status`, `terminal`, `run_token`, `worker_instance_id`, and
`elapsed_clock: worker_monotonic`.
`elapsed_ms` measures time since this worker attempt started, at event emission.
It is nondecreasing within one `worker_instance_id` stream. Each worker invocation
has a fresh ID and clock origin, including a rejected duplicate carrying the
same `run_token`. The token governs ownership; the instance ID only identifies
an event emitter. Buffered timing records retain their stage `duration_ms` but
use their emission time for `elapsed_ms`.

Graph progress has `scope: graph`, retains `graph_phase` and the graph-relative
`graph_elapsed_ms`, and is nonterminal at the job level. Graph completion and
failure use `phase: graph_complete` and `graph_failed`; neither means the job has
finished. Stage timing records have `scope: stage`. A rejected or displaced
worker has `scope: attempt`, so its failure does not claim the current job failed.
The `status` on nonterminal progress describes running work, not an authoritative
status snapshot; use the status/result APIs for current state.

Only after the worker has accepted the canonical result and complete status does
it emit `scope: job, phase: complete, status: complete, terminal: true`. Job
failure and cancellation likewise follow their persisted status transition.
Events are diagnostics, not result authority: a crash can occur after acceptance
but before the completion event is written. Historical rows without the new
fields may contain graph-relative clocks and an early ambiguous `complete` phase.
Do not infer accepted results from those rows. Standalone graph progress and the
synchronous CLI/MCP graph diagnostics retain their existing phases and clock.

## Recovery and cancellation

`resume_router_job(job_id)` reloads the original request and starts a new worker
for stale, failed, or cancelled jobs. The worker re-runs repository discovery and
calls the real graph/router build path, so the repository universe and graph cache
freshness are revalidated on each attempt.

`cancel_router_job(job_id)` creates a cooperative cancel marker inside that job's
own directory and marks only that job as `cancellation_requested` while a worker
may still be running. The worker checks the marker between progress events and
before publishing the final result, then acknowledges with `cancelled` without
producing router content. If a worker wins the final race and seals a complete
result before cancellation is applied, the complete result is preserved. If
recovery later finds that a worker stopped without a sealed complete result or
worker cancellation acknowledgment, the status becomes `failed`.

Each worker attempt has a random `run_token`, an exclusive OS-held worker lock,
and a diagnostic heartbeat. Resume treats the held worker lock as liveness
authority and uses a separate state lock to serialize parent status changes.
Heartbeat freshness alone is not authority to steal or preserve an attempt. PIDs
are diagnostic in durable receipts and are not used as authority for cancellation
or resume correctness.

The worker writes attempt-scoped output first, then publishes the canonical
`router.md` and terminal status under the same state lock after revalidating the
current `run_token`, status, cancellation marker, and result-path safety. A stale
worker cannot overwrite a newer complete result.

## CLI/MCP

The background commands use the same build functions as the synchronous router:

```text
index router-job start --root ROOT [--max-docs N] [--budget-ms N] [--no-cache]
index router-job status JOB_ID
index router-job result JOB_ID
index router-job cancel JOB_ID
index router-job resume JOB_ID
```

MCP exposes the same five operations:

```text
index.router.job.start   {root, max_docs?, budget_ms?, no_cache?}
index.router.job.status  {job_id}
index.router.job.result  {job_id}
index.router.job.cancel  {job_id}
index.router.job.resume  {job_id}
```

`start` returns a running status receipt. `status` returns the current receipt and
performs stale-worker recovery checks. `result` returns router text only for a
complete job; otherwise it returns a typed non-complete receipt. `cancel` is
cooperative by default. `resume` restarts only stale or terminal non-complete
jobs; live attempts return their existing receipt.

## Boundary

Router jobs reuse the existing Index functions: repository discovery semantics,
`build_graph`, graph cache validation, doc discovery, router pack assembly, and
router rendering. The operation-local router inventory is only a listing cache:
it does not replace exact working-byte hashing, does not persist source metadata
as freshness authority, and does not add a new server, database, dependency, or
alternate graph implementation.
