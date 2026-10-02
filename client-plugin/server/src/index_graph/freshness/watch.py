"""watch.py — incremental auto-resync: the live drift verdict competitors have,
plus the receipt they don't.

Every codebase-map tool in the category auto-syncs on file change; index did
not, so its freshness was baseline-only (the workbench Health view says as much
honestly). This closes that gap by COMPOSING the freshness machinery rather
than adding new state: a watcher holds the prior workspace fingerprint, and on
each tick recomputes the current one and runs the pure `compare_freshness`. The
retained prior snapshot is exactly what turns "current fingerprint only" into a
real FRESH/STALE verdict — the thing a single --root pass cannot emit.

Every resync emits a re-checkable sync receipt (schema below): the two
fingerprint roots, the verdict, and the named repo deltas. A consumer recomputes
the fingerprint and re-runs compare_freshness to confirm it — the watcher never
asks to be trusted.

Zero dependencies: stdlib polling (mtime + the content fingerprint that already
exists), no OS file-event API, no watchdog package. Poll cadence is a floor on
latency, not a correctness property — the fingerprint is authoritative, so a
missed poll only delays a verdict, never fabricates one.

Robustness: a rescan that raises (a file vanishing mid-walk, a permission flip)
is caught and reported as an errored tick, never crashing the loop; the prior
good fingerprint is retained so the next tick recovers.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path

from .compare import compare_freshness
from .fingerprint import workspace_fingerprint

SYNC_SCHEMA = "index.freshness-sync/1"


def _now(clock: Callable[[], float] | None) -> float:
    return (clock or time.time)()


def sync_report(prev: dict, curr: dict, *, tick: int, at: float,
                changed_paths: list[str] | None = None) -> dict:
    """One re-checkable resync receipt. `prev`/`curr` are index.freshness/1
    fingerprints; the verdict is the pure compare over them."""
    cmp = compare_freshness(prev, curr)
    return {
        "schema": SYNC_SCHEMA,
        "tick": tick,
        "at": round(at, 3),
        "verdict": cmp["verdict"],                 # FRESH | STALE
        "prev_root": cmp["stamp_root"],
        "curr_root": cmp["current_root"],
        "repos_added": cmp["repos_added"],
        "repos_removed": cmp["repos_removed"],
        "repos_changed": cmp["repos_changed"],
        "changed_paths": sorted(changed_paths) if changed_paths else [],
        "recheck": "index freshness --root ROOT  (recompute the fingerprint and re-compare)",
    }


def diff_changed_paths(prev_paths: dict[str, str], curr_paths: dict[str, str]) -> list[str]:
    """Which relevant files changed between two path->sha maps (for the receipt's
    detail line). Optional; the verdict never depends on it."""
    out = []
    for p in set(prev_paths) | set(curr_paths):
        if prev_paths.get(p) != curr_paths.get(p):
            out.append(p)
    return out


def watch_iter(
    repo_paths: dict[str, Path],
    *,
    interval: float = 2.0,
    max_ticks: int | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    on_change: Callable[[dict], None] | None = None,
) -> Iterator[dict]:
    """Yield a sync receipt for every tick on which the workspace fingerprint
    changed (STALE), plus the initial baseline tick. Deterministic and testable:
    inject `sleep`/`clock`; bound with `max_ticks`. `repo_paths` is re-read each
    tick so newly added/removed repos are picked up by the caller-supplied map.

    The first yielded receipt is the baseline (tick 0, verdict FRESH vs itself).
    Thereafter only ticks that DETECTED a change are yielded, so a consumer that
    regenerates an artifact runs only when something actually moved."""
    sleep = sleep or time.sleep
    prev = _safe_fingerprint(repo_paths)
    baseline = sync_report(prev, prev, tick=0, at=_now(clock))
    if on_change:
        on_change(baseline)
    yield baseline
    tick = 0
    while max_ticks is None or tick < max_ticks:
        sleep(interval)
        tick += 1
        curr = _safe_fingerprint(repo_paths)
        if curr is None:                            # errored rescan: retain prev, report, continue
            yield {"schema": SYNC_SCHEMA, "tick": tick, "at": round(_now(clock), 3),
                   "verdict": "UNVERIFIABLE", "error": "fingerprint rescan failed",
                   "prev_root": prev.get("root")}
            continue
        if curr.get("root") != prev.get("root"):
            report = sync_report(prev, curr, tick=tick, at=_now(clock))
            prev = curr
            if on_change:
                on_change(report)
            yield report
        # FRESH ticks are silent by design (no yield): only movement is reported


def _safe_fingerprint(repo_paths: dict[str, Path]):
    try:
        return workspace_fingerprint(repo_paths)
    except Exception:                               # never let a transient FS error kill the loop
        return None
