"""Path selection with typed rejection receipts (index.path-selection/v1).

Every path the selector considers lands in exactly one of two buckets:
selected, or rejected with a typed receipt naming a reason code from a
closed set and the rule that dropped it. Counts must reconcile
(candidates == selected + rejected), and ``reconcile_selection``
re-derives that ledger from the lists themselves, so a silent drop, a
forged count, or an untyped rejection is machine-detectable. A selector
that cannot show what it dropped is not auditable.
"""
from __future__ import annotations

import copy
import json
import os
from collections import Counter
from pathlib import Path

from ..graph.walk import EXCLUDE_DIRS

RECEIPT_SCHEMA = "index.path-selection/v1"
RESULT_SCHEMA = "index.path-selection-result/v1"
RECONCILIATION_SCHEMA = "index.path-selection-reconciliation/v1"

# The closed set of rejection reason codes. The validator refuses anything
# outside it; a new code is added here, never invented at a call site.
REASON_CODES = frozenset({
    "excluded-by-rule",   # a directory pruned by the shared EXCLUDE_DIRS rule
    "suffix-mismatch",    # a file whose suffix is outside the requested set
    "over-budget",        # a file beyond the max_files budget
    "not-found",          # the selection root does not exist
    "unreadable",         # a selected file that failed the read probe
})

_RECEIPT_FIELDS = ("schema", "path", "reason_code", "rule_ref")
_EXCLUDE_RULE_REF = "index_graph.graph.walk.EXCLUDE_DIRS"


def _receipt(path: str, reason_code: str, rule_ref: str) -> dict:
    return {"schema": RECEIPT_SCHEMA, "path": path,
            "reason_code": reason_code, "rule_ref": rule_ref}


def _result(rules: dict, selected: list[str], rejected: list[dict]) -> dict:
    return {
        "schema": RESULT_SCHEMA,
        "rules": rules,
        "selected": selected,
        "rejected": rejected,
        "counts": {"candidates": len(selected) + len(rejected),
                   "selected": len(selected), "rejected": len(rejected)},
    }


def _walk_candidates(root: Path):
    """Yield (relative_posix_path, pruned) for every candidate under root.

    A pruned entry is a directory dropped by EXCLUDE_DIRS. It counts as one
    candidate and carries one receipt, and nothing beneath it is walked, so
    a buried file can never bypass the directory's receipt.
    """
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        base = Path(dirpath)
        for name in sorted(d for d in dirnames if d in EXCLUDE_DIRS):
            yield (base / name).relative_to(root).as_posix(), True
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            yield (base / name).relative_to(root).as_posix(), False


def select_paths(root: Path | str, suffixes: tuple[str, ...] | None = None,
                 max_files: int | None = None) -> dict:
    """Split every candidate under ``root`` into selected or rejected.

    ``suffixes`` keeps only files ending in one of the given suffixes
    (None keeps every file). ``max_files`` is a budget: files beyond it
    are rejected with over-budget receipts, never silently dropped.
    """
    if max_files is not None and max_files < 0:
        raise ValueError("max_files must be >= 0")
    root = Path(root)
    rules = {"suffixes": list(suffixes) if suffixes else None,
             "max_files": max_files}
    if not root.is_dir():
        return _result(rules, [], [_receipt(".", "not-found", "select.root")])
    selected: list[str] = []
    rejected: list[dict] = []
    for rel, pruned in _walk_candidates(root):
        if pruned:
            rejected.append(_receipt(rel, "excluded-by-rule", _EXCLUDE_RULE_REF))
        elif suffixes is not None and not rel.endswith(tuple(suffixes)):
            rejected.append(_receipt(rel, "suffix-mismatch",
                                     "select.suffixes:" + ",".join(suffixes)))
        else:
            selected.append(rel)
    selected.sort()
    if max_files is not None and len(selected) > max_files:
        for rel in selected[max_files:]:
            rejected.append(_receipt(rel, "over-budget",
                                     f"select.max_files:{max_files}"))
        selected = selected[:max_files]
    rejected.sort(key=lambda receipt: receipt["path"])
    return _result(rules, selected, rejected)


def validate_receipt(receipt: object) -> list[str]:
    """Return every reason ``receipt`` is not a valid rejection receipt.

    An empty list means valid. The check is closed-world: the exact schema
    id, exactly the four typed fields, and a reason code from REASON_CODES.
    """
    if not isinstance(receipt, dict):
        return [f"receipt must be an object, got {type(receipt).__name__}"]
    errors: list[str] = []
    unknown = sorted(set(receipt) - set(_RECEIPT_FIELDS))
    if unknown:
        errors.append("unknown fields: " + ", ".join(unknown))
    for field in _RECEIPT_FIELDS:
        if field not in receipt:
            errors.append(f"missing field: {field}")
        elif not isinstance(receipt[field], str) or not receipt[field]:
            errors.append(f"{field} must be a non-empty string")
    schema = receipt.get("schema")
    if isinstance(schema, str) and schema and schema != RECEIPT_SCHEMA:
        errors.append(f"schema must be {RECEIPT_SCHEMA}, got {schema!r}")
    code = receipt.get("reason_code")
    if isinstance(code, str) and code and code not in REASON_CODES:
        errors.append(f"unknown reason_code: {code!r} "
                      f"(closed set: {', '.join(sorted(REASON_CODES))})")
    return errors


def reconcile_selection(selection: object) -> dict:
    """Re-derive the selection ledger from its own lists; DRIFT on any gap.

    MATCH is earned, never declared: the declared counts must equal the
    list lengths, candidates must equal selected + rejected, every receipt
    must validate against the closed reason-code set, and no path may be
    booked twice across selected and rejected.
    """
    if not isinstance(selection, dict) or selection.get("schema") != RESULT_SCHEMA:
        return _report([{"code": "result-schema",
                         "detail": f"selection schema must be {RESULT_SCHEMA}"}])
    failures: list[dict] = []
    selected = selection.get("selected") or []
    rejected = selection.get("rejected") or []
    counts = selection.get("counts") or {}
    if counts.get("candidates") != counts.get("selected", 0) + counts.get("rejected", 0):
        failures.append({"code": "counts-mismatch",
                         "detail": (f"declared candidates={counts.get('candidates')} != "
                                    f"selected={counts.get('selected')} + "
                                    f"rejected={counts.get('rejected')}")})
    if counts.get("selected") != len(selected):
        failures.append({"code": "selected-count-mismatch",
                         "detail": (f"declared selected={counts.get('selected')} "
                                    f"but the list holds {len(selected)}")})
    if counts.get("rejected") != len(rejected):
        failures.append({"code": "rejected-count-mismatch",
                         "detail": (f"declared rejected={counts.get('rejected')} but the "
                                    f"list holds {len(rejected)} receipt(s); a rejection "
                                    "without a receipt is a silent drop")})
    for receipt in rejected:
        errors = validate_receipt(receipt)
        if errors:
            path = receipt.get("path", "?") if isinstance(receipt, dict) else "?"
            failures.append({"code": "invalid-receipt",
                             "detail": f"{path}: " + "; ".join(errors)})
    booked = Counter(list(selected)
                     + [r.get("path") for r in rejected if isinstance(r, dict)])
    for path, times in sorted(booked.items(), key=lambda item: str(item[0])):
        if times > 1 and path is not None:
            failures.append({"code": "duplicate-path",
                             "detail": f"path booked {times} times: {path}"})
    return _report(failures)


def _report(failures: list[dict]) -> dict:
    return {"schema": RECONCILIATION_SCHEMA,
            "verdict": "MATCH" if not failures else "DRIFT",
            "failures": failures}


def reject_selected(selection: dict, path: str, reason_code: str,
                    rule_ref: str) -> dict:
    """Move ``path`` from selected to rejected, leaving a typed receipt.

    Refuses reason codes outside the closed set and paths that are not
    currently selected, so a caller cannot mint receipts for paths the
    selection never held. Candidates are conserved.
    """
    if reason_code not in REASON_CODES:
        raise ValueError(f"unknown reason_code: {reason_code!r}")
    if path not in selection["selected"]:
        raise ValueError(f"path is not selected: {path!r}")
    selection["selected"].remove(path)
    receipt = _receipt(path, reason_code, rule_ref)
    selection["rejected"].append(receipt)
    selection["counts"]["selected"] -= 1
    selection["counts"]["rejected"] += 1
    return receipt


def _read_probe(path: Path) -> None:
    """Raise OSError if ``path`` cannot actually be opened and read."""
    with path.open("rb") as handle:
        handle.read(1)


def probe_readable(selection: dict, root: Path | str) -> dict:
    """Return a copy of ``selection`` where files failing the read probe
    have moved to rejected with unreadable receipts. Probing reclassifies;
    it never drops, so the candidate count is conserved."""
    root = Path(root)
    probed = copy.deepcopy(selection)
    for rel in list(probed["selected"]):
        try:
            _read_probe(root / rel)
        except OSError:
            reject_selected(probed, rel, "unreadable", "select.read_check")
    return probed


def run_select(root: Path | str, suffixes: tuple[str, ...] | None,
               max_files: int | None) -> dict:
    """Select, probe readability, reconcile: the shared CLI/MCP payload."""
    selection = probe_readable(
        select_paths(root, suffixes=suffixes, max_files=max_files), root)
    return {"selection": selection,
            "reconciliation": reconcile_selection(selection)}


def cmd_select(args) -> int:
    """CLI face: print the selection and its reconciliation report."""
    if args.max_files is not None and args.max_files < 0:
        raise SystemExit("--max-files must be >= 0")
    suffixes = tuple(args.suffixes) if args.suffixes else None
    payload = run_select(args.root.resolve(), suffixes, args.max_files)
    selection, report = payload["selection"], payload["reconciliation"]
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        counts = selection["counts"]
        print(f"select verdict={report['verdict']} "
              f"candidates={counts['candidates']} "
              f"selected={counts['selected']} rejected={counts['rejected']}")
        reasons = Counter(r["reason_code"] for r in selection["rejected"])
        for code, count in sorted(reasons.items()):
            print(f"  {code}: {count}")
        for failure in report["failures"]:
            print(f"  [{failure['code']}] {failure['detail']}")
    return 0 if report["verdict"] == "MATCH" else 1
