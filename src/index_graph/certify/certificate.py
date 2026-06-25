"""The verdict certificate: re-checkable, three answers, never a fourth.

A consumer believes a certificate by re-running its `recheck` command,
recomputing the hashes, and confirming the verdict. There is no TRUSTED.
"""
from __future__ import annotations

import hashlib
import json

_VERDICTS = frozenset({"MATCH", "DRIFT", "UNVERIFIABLE"})


def canonical_sha(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build_certificate(kind: str, *, content: dict, criterion: dict | None,
                      verdict: str, findings: list[dict], recheck: str,
                      tool_version: str) -> dict:
    if verdict not in _VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(_VERDICTS)}, got {verdict!r}")
    return {
        "schema": "index.certificate/1",
        "tool_version": tool_version,
        "kind": kind,
        "content_sha256": canonical_sha(content),
        "criterion_sha256": canonical_sha(criterion) if criterion is not None else None,
        "verdict": verdict,
        "findings": findings,
        "recheck": recheck,
    }
