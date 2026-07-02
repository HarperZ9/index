"""Typed invalidation reports: the diff that names what it invalidates.

`index freshness` says THAT the workspace moved; `index.invalidation/1`
says WHAT that movement invalidates. A pin (`index.invalidation-pin/1`)
records per-file hashes plus the structural snapshot at mint time.
Comparing it against the current tree lands every fingerprinted artifact
or scope in exactly one of two buckets: invalidated, with a reason code
from a closed set, or still valid. Counts must reconcile (invalidated +
still_valid == fingerprinted scope), and `reconcile_invalidation`
re-derives that ledger from the report itself, so a forged count, an
unknown reason code, or a double-booked scope is machine-detectable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..certify import canonical_sha
from .fingerprint import relevant_files

PIN_SCHEMA = "index.invalidation-pin/1"
REPORT_SCHEMA = "index.invalidation/1"
RECONCILIATION_SCHEMA = "index.invalidation-reconciliation/1"

# The closed set of invalidation reason codes. A new code is added here,
# never invented at a call site.
REASON_CODES = frozenset({
    "file-changed",             # a pinned graph-relevant file's content moved
    "file-removed",             # a pinned graph-relevant file is gone
    "dependency-edge-changed",  # the structural snapshot (edges/roles/cycles) moved
    "doc-changed",              # a pinned doc the context pack reads moved
    "unversioned",              # content now in scope that the pin never versioned
})

# The derived artifacts index fingerprints, invalidated as workspace-level scopes.
ARTIFACTS = ("certificate", "context-pack", "graph-snapshot")

# The docs the context pack reads (repo descriptions come from these).
DOC_NAMES = ("README.md", "README.rst", "README.txt", "readme.md")

EVIDENCE_LIMIT = 5

# Most severe first: aggregation picks the first code its inputs contain.
_REASON_PRIORITY = ("file-removed", "file-changed", "dependency-edge-changed",
                    "doc-changed", "unversioned")


def _hash_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "unreadable"


def _repo_state(repo_root: Path) -> dict:
    """Per-file hashes for one repo: the graph-relevant files the resolvers
    read, and the root docs the context pack reads. Fail-closed: a missing
    tree yields empty maps rather than raising."""
    root = Path(repo_root)
    graph_files: dict[str, str] = {}
    for p in relevant_files(root):
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        graph_files[rel] = _hash_file(p)
    try:
        entries = {p.name for p in root.iterdir() if p.is_file()}
    except OSError:
        entries = set()
    doc_files = {name: _hash_file(root / name) for name in DOC_NAMES if name in entries}
    return {"graph_files": graph_files, "doc_files": doc_files}


def _pin_state(repo_paths: dict[str, Path], snapshot: dict) -> dict:
    return {"repos": {name: _repo_state(path)
                      for name, path in sorted(repo_paths.items())},
            "snapshot": snapshot}


def _workspace_inputs(root: Path) -> tuple[dict[str, Path], dict]:
    from ..config import load_config
    from ..context.pack import to_json
    from ..drift import snapshot_pack
    from ..graph.build import build_graph
    from ..scan import discover_repos
    repo_paths = {p.name: p for p in discover_repos(Path(root), load_config(None, Path(root)))}
    return repo_paths, snapshot_pack(to_json(build_graph(repo_paths)))


def mint_pin(root: Path | str) -> dict:
    """Pin the current tree: per-file hashes plus the structural snapshot,
    content-addressed by ``pinned_ref`` (the canonical SHA-256 of the state,
    per docs/PROTOCOL.md hashing)."""
    from .. import __version__
    state = _pin_state(*_workspace_inputs(Path(root)))
    return {"schema": PIN_SCHEMA, "tool_version": __version__,
            "pinned_ref": canonical_sha(state), **state}


def _split(pinned: dict, current: dict) -> tuple[list[str], list[str], list[str]]:
    """(removed, changed, added) keys between two {path: sha} maps."""
    removed = sorted(set(pinned) - set(current))
    added = sorted(set(current) - set(pinned))
    changed = sorted(k for k in set(pinned) & set(current) if pinned[k] != current[k])
    return removed, changed, added


def _repo_reason(pinned: dict, current: dict) -> tuple[str | None, list[str]]:
    """The single most severe reason a pinned repo scope moved, with evidence."""
    removed, changed, added = _split(pinned.get("graph_files", {}),
                                     current.get("graph_files", {}))
    doc_removed, doc_changed, doc_added = _split(pinned.get("doc_files", {}),
                                                 current.get("doc_files", {}))
    if removed:
        return "file-removed", removed[:EVIDENCE_LIMIT]
    if changed:
        return "file-changed", changed[:EVIDENCE_LIMIT]
    if added:
        return "unversioned", added[:EVIDENCE_LIMIT]
    docs = sorted(set(doc_removed) | set(doc_changed) | set(doc_added))
    if docs:
        return "doc-changed", docs[:EVIDENCE_LIMIT]
    return None, []


def _snapshot_reason(pinned: dict, current: dict) -> tuple[str | None, list[str]]:
    """Why the structural snapshot no longer holds, or None when it does."""
    old_edges, new_edges = set(pinned.get("edges", [])), set(current.get("edges", []))
    if old_edges != new_edges:
        diff = sorted(f"- {e}" for e in old_edges - new_edges)
        diff += sorted(f"+ {e}" for e in new_edges - old_edges)
        return "dependency-edge-changed", diff[:EVIDENCE_LIMIT]
    old_repos, new_repos = set(pinned.get("repos", [])), set(current.get("repos", []))
    if old_repos - new_repos:
        return "file-removed", sorted(old_repos - new_repos)[:EVIDENCE_LIMIT]
    if new_repos - old_repos:
        return "unversioned", sorted(new_repos - old_repos)[:EVIDENCE_LIMIT]
    if pinned != current:  # roles or cycles moved with identical edge strings
        return "dependency-edge-changed", []
    return None, []


def _aggregate(reasons: dict[str, list[str]]) -> tuple[str, list[str]]:
    """Fold contributing reasons into the single most severe one."""
    for code in _REASON_PRIORITY:
        if code in reasons:
            return code, list(dict.fromkeys(reasons[code]))[:EVIDENCE_LIMIT]
    raise ValueError("aggregate called with no reasons")  # pragma: no cover


def _item(scope: str, reason: str, evidence: list[str]) -> dict:
    return {"artifact_or_scope": scope, "reason_code": reason, "evidence": evidence}


def invalidation_report(pin: dict, root: Path | str, *, recheck: str | None = None) -> dict:
    """Diff the pinned state against the current tree and name what it invalidates.

    A tampered pin hash simply reads as a moved file (STALE, file-changed);
    only a document that is not a pin at all raises ValueError.
    """
    if (not isinstance(pin, dict) or pin.get("schema") != PIN_SCHEMA
            or not isinstance(pin.get("repos"), dict)
            or not isinstance(pin.get("snapshot"), dict)):
        raise ValueError(f"pin is not an {PIN_SCHEMA} document")
    repo_paths, current_snapshot = _workspace_inputs(Path(root))
    current = _pin_state(repo_paths, current_snapshot)
    invalidated: list[dict] = []
    derived: dict[str, list[str]] = {}  # reasons feeding certificate + context-pack
    for name in sorted(pin["repos"]):
        reason, evidence = _repo_reason(pin["repos"][name],
                                        current["repos"].get(name, {}))
        if reason:
            invalidated.append(_item(f"repo:{name}", reason, evidence))
            derived.setdefault(reason, []).extend(evidence or [f"repo:{name}"])
    snap_reason, snap_evidence = _snapshot_reason(pin["snapshot"], current_snapshot)
    if snap_reason:
        invalidated.append(_item("graph-snapshot", snap_reason, snap_evidence))
        derived.setdefault(snap_reason, []).extend(snap_evidence or ["graph-snapshot"])
    new_repos = sorted(set(current["repos"]) - set(pin["repos"]))
    if new_repos:
        derived.setdefault("unversioned", []).extend(new_repos)
    if derived:
        reason, evidence = _aggregate(derived)
        invalidated.append(_item("certificate", reason, evidence))
        invalidated.append(_item("context-pack", reason, evidence))
    invalidated.sort(key=lambda item: item["artifact_or_scope"])
    scope = sorted(list(ARTIFACTS) + [f"repo:{name}" for name in pin["repos"]])
    named = {item["artifact_or_scope"] for item in invalidated}
    still_valid = [entry for entry in scope if entry not in named]
    return {
        "schema": REPORT_SCHEMA,
        "pinned_ref": pin.get("pinned_ref"),
        "current_ref": canonical_sha(current),
        "verdict": "FRESH" if not invalidated else "STALE",
        "invalidated": invalidated,
        "still_valid": still_valid,
        "counts": {"scope": len(scope), "invalidated": len(invalidated),
                   "still_valid": len(still_valid)},
        "recheck": recheck or "index invalidate --root ROOT --pin PIN --json",
    }


def reconcile_invalidation(report: object) -> dict:
    """Re-derive the invalidation ledger from the report itself; DRIFT on any gap.

    MATCH is earned, never declared: declared counts must equal the list
    lengths, invalidated + still_valid must equal the fingerprinted scope,
    every reason code must come from the closed set, no scope may be booked
    twice, and the verdict must agree with the lists it sits over.
    """
    if not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA:
        return _reconciliation([{"code": "report-schema",
                                 "detail": f"report schema must be {REPORT_SCHEMA}"}])
    invalidated = report.get("invalidated") or []
    still_valid = report.get("still_valid") or []
    failures = _count_failures(report.get("counts") or {}, invalidated, still_valid)
    booked: dict[str, int] = {}
    for item in invalidated:
        scope_name = item.get("artifact_or_scope") if isinstance(item, dict) else None
        code = item.get("reason_code") if isinstance(item, dict) else None
        if code not in REASON_CODES:
            failures.append({"code": "unknown-reason-code",
                             "detail": (f"{scope_name or '?'}: {code!r} (closed set: "
                                        f"{', '.join(sorted(REASON_CODES))})")})
        if scope_name is not None:
            booked[scope_name] = booked.get(scope_name, 0) + 1
    for scope_name in still_valid:
        booked[scope_name] = booked.get(scope_name, 0) + 1
    for scope_name, times in sorted(booked.items(), key=lambda kv: str(kv[0])):
        if times > 1:
            failures.append({"code": "duplicate-scope",
                             "detail": f"scope booked {times} times: {scope_name}"})
    verdict = report.get("verdict")
    if verdict == "UNVERIFIABLE":
        if invalidated or still_valid:
            failures.append({"code": "verdict-mismatch",
                             "detail": "an UNVERIFIABLE report must carry no scope entries"})
    elif verdict != ("FRESH" if not invalidated else "STALE"):
        failures.append({"code": "verdict-mismatch",
                         "detail": (f"verdict {verdict!r} over "
                                    f"{len(invalidated)} invalidation(s)")})
    return _reconciliation(failures)


def _count_failures(counts: dict, invalidated: list, still_valid: list) -> list[dict]:
    """The declared-count checks: the ledger must add up before anything else."""
    failures: list[dict] = []
    if counts.get("scope") != counts.get("invalidated", 0) + counts.get("still_valid", 0):
        failures.append({"code": "counts-mismatch",
                         "detail": (f"declared scope={counts.get('scope')} != "
                                    f"invalidated={counts.get('invalidated')} + "
                                    f"still_valid={counts.get('still_valid')}")})
    if counts.get("invalidated") != len(invalidated):
        failures.append({"code": "invalidated-count-mismatch",
                         "detail": (f"declared invalidated={counts.get('invalidated')} "
                                    f"but the list holds {len(invalidated)}")})
    if counts.get("still_valid") != len(still_valid):
        failures.append({"code": "still-valid-count-mismatch",
                         "detail": (f"declared still_valid={counts.get('still_valid')} "
                                    f"but the list holds {len(still_valid)}")})
    return failures


def _reconciliation(failures: list[dict]) -> dict:
    return {"schema": RECONCILIATION_SCHEMA,
            "verdict": "MATCH" if not failures else "DRIFT",
            "failures": failures}
