"""Aggregate graph-cache telemetry without source or path disclosure."""
from __future__ import annotations

from time import perf_counter

CACHE_STAGE_KEYS = (
    "fingerprint",
    "fingerprint_walk",
    "fingerprint_read_hash",
    "description_read_hash",
    "resolver_signature",
    "cache_read",
    "cache_decode",
    "cache_rehydrate",
    "fresh_build",
    "cache_write",
)
FINGERPRINT_KEYS = (
    "files",
    "bytes",
    "unreadable",
    "description_files",
    "description_bytes",
    "description_unreadable",
)


def empty_repo_cache_stats() -> dict[str, int]:
    stats = {f"{key}_ms": 0 for key in CACHE_STAGE_KEYS}
    stats.update({f"fingerprint_{key}": 0 for key in FINGERPRINT_KEYS})
    return stats


def add_cache_stat(stats: dict[str, int] | None, key: str, value: int) -> None:
    if stats is not None:
        stats[key] = int(stats.get(key, 0)) + int(value)


def add_cache_timing(stats: dict[str, int] | None, key: str, started: float) -> None:
    add_cache_stat(stats, f"{key}_ms", int((perf_counter() - started) * 1000))


def empty_cache_summary() -> dict[str, object]:
    return {
        "hits": 0,
        "misses": 0,
        "invalid": 0,
        "bypassed": 0,
        "writes": 0,
        "reasons": {},
        "stage_timings_ms": {key: 0 for key in CACHE_STAGE_KEYS},
        "fingerprint": {key: 0 for key in FINGERPRINT_KEYS},
    }


def record_cache_summary(
    summary: dict[str, object],
    outcome: str,
    reason: str,
    written: bool,
    stats: dict[str, int] | None = None,
) -> None:
    outcome_to_key = {"hit": "hits", "miss": "misses", "invalid": "invalid", "bypassed": "bypassed"}
    key = outcome_to_key.get(outcome, "invalid")
    summary[key] = int(summary.get(key, 0)) + 1
    if written:
        summary["writes"] = int(summary.get("writes", 0)) + 1
    reasons = summary.setdefault("reasons", {})
    if isinstance(reasons, dict):
        reasons[reason or outcome] = int(reasons.get(reason or outcome, 0)) + 1
    stage_timings = summary.setdefault("stage_timings_ms", {})
    if isinstance(stage_timings, dict):
        for stage_key in CACHE_STAGE_KEYS:
            stage_timings[stage_key] = int(stage_timings.get(stage_key, 0)) + int((stats or {}).get(f"{stage_key}_ms", 0))
    fingerprint = summary.setdefault("fingerprint", {})
    if isinstance(fingerprint, dict):
        for stat_key in FINGERPRINT_KEYS:
            fingerprint[stat_key] = int(fingerprint.get(stat_key, 0)) + int((stats or {}).get(f"fingerprint_{stat_key}", 0))


def final_cache_summary(summary: dict[str, object]) -> dict[str, object]:
    reasons = summary.get("reasons")
    stage_timings = summary.get("stage_timings_ms")
    fingerprint = summary.get("fingerprint")
    return {
        "hits": int(summary.get("hits", 0)),
        "misses": int(summary.get("misses", 0)),
        "invalid": int(summary.get("invalid", 0)),
        "bypassed": int(summary.get("bypassed", 0)),
        "writes": int(summary.get("writes", 0)),
        "reasons": dict(sorted(reasons.items())) if isinstance(reasons, dict) else {},
        "stage_timings_ms": {
            key: int(stage_timings.get(key, 0)) if isinstance(stage_timings, dict) else 0
            for key in CACHE_STAGE_KEYS
        },
        "fingerprint": {
            key: int(fingerprint.get(key, 0)) if isinstance(fingerprint, dict) else 0
            for key in FINGERPRINT_KEYS
        },
    }
