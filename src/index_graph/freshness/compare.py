"""Compare a recorded freshness stamp against the live workspace fingerprint."""
from __future__ import annotations

from .fingerprint import SCHEMA

REPORT_SCHEMA = "index.freshness-report/1"


def compare_freshness(stamp: dict, current: dict) -> dict:
    """FRESH if every repo fingerprint matches; STALE with named deltas otherwise.

    Pure (no I/O), so the report is re-checkable: a consumer recomputes the
    current fingerprint and runs this again. Raises ValueError if either side
    is not an index.freshness/1 document.
    """
    for doc, who in ((stamp, "stamp"), (current, "current")):
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            raise ValueError(f"{who} is not an {SCHEMA} document")
    s_repos = stamp.get("repos", {})
    c_repos = current.get("repos", {})
    added = sorted(set(c_repos) - set(s_repos))
    removed = sorted(set(s_repos) - set(c_repos))
    changed = sorted(n for n in (set(s_repos) & set(c_repos)) if s_repos[n] != c_repos[n])
    fresh = not (added or removed or changed)
    return {
        "schema": REPORT_SCHEMA,
        "verdict": "FRESH" if fresh else "STALE",
        "stamp_root": stamp.get("root"),
        "current_root": current.get("root"),
        "repos_added": added,
        "repos_removed": removed,
        "repos_changed": changed,
    }
