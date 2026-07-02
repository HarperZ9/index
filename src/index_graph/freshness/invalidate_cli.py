"""CLI and shared-payload face for the typed invalidation report.

`index invalidate --out PIN` mints a pin of the current tree;
`index invalidate --pin PIN` diffs it against the tree and emits the
`index.invalidation/1` report plus its reconciliation. The MCP tool
reuses `run_invalidate` and `mint_pin`, so the protocol face never
disagrees with the CLI.
"""
from __future__ import annotations

import json
from pathlib import Path

from .invalidate import (
    REPORT_SCHEMA,
    invalidation_report,
    mint_pin,
    reconcile_invalidation,
)

_EXIT = {"FRESH": 0, "STALE": 1, "UNVERIFIABLE": 2}


def _unverifiable(detail: str, recheck: str | None) -> dict:
    return {"schema": REPORT_SCHEMA, "pinned_ref": None, "current_ref": None,
            "verdict": "UNVERIFIABLE", "detail": detail,
            "invalidated": [], "still_valid": [],
            "counts": {"scope": 0, "invalidated": 0, "still_valid": 0},
            "recheck": recheck or "index invalidate --root ROOT --pin PIN --json"}


def run_invalidate(root: Path | str, pin: dict, *, recheck: str | None = None) -> dict:
    """Report + reconciliation: the shared CLI/MCP payload.

    A document that is not a pin yields an UNVERIFIABLE report, not a crash;
    a tampered pin yields STALE with file-changed reasons.
    """
    try:
        report = invalidation_report(pin, root, recheck=recheck)
    except ValueError as exc:
        report = _unverifiable(str(exc), recheck)
    return {"report": report, "reconciliation": reconcile_invalidation(report)}


def cmd_invalidate(args) -> int:
    """CLI face: mint a pin with --out, or report against one with --pin."""
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    if (args.out is None) == (args.pin is None):
        raise SystemExit(
            "invalidate: pass exactly one of --out PIN (mint) or --pin PIN (report)")
    if args.out is not None:
        pin = mint_pin(root)
        args.out.write_text(json.dumps(pin, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote {args.out} repos={len(pin['repos'])} "
              f"pinned_ref={pin['pinned_ref'][:12]}")
        return 0
    try:
        pin = json.loads(args.pin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalidate: cannot read pin {args.pin}: {exc}")
    recheck = f'index invalidate --root "{args.root}" --pin "{args.pin}" --json'
    payload = run_invalidate(root, pin, recheck=recheck)
    report = payload["report"]
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        counts = report["counts"]
        line = (f"invalidation verdict={report['verdict']} scope={counts['scope']} "
                f"invalidated={counts['invalidated']} "
                f"still_valid={counts['still_valid']}")
        if report.get("detail"):
            line += f": {report['detail']}"
        print(line)
        for item in report["invalidated"]:
            print(f"  {item['artifact_or_scope']}: {item['reason_code']}")
        for failure in payload["reconciliation"]["failures"]:
            print(f"  [{failure['code']}] {failure['detail']}")
    return _EXIT[report["verdict"]]
