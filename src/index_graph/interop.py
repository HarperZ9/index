"""Interop: index's context envelopes as organ-bundle interchange entries.

The organ bundle is the shared spine gather, crucible, forum, learn, and index
compose on. This module maps index's context envelopes (the budgeted,
receipt-backed context packs) into that entry shape, so an index envelope can
feed the agent loop, compose into forum's routing context, or back a learn
lesson through the shared spine.

Entry shape matches the proof-surface organ-bundle contract
(entry_id, organ_id, receipt_kind, status, payload_sha256, summary, payload_ref).
gather/src/gather/interop.py is the reference implementation.
"""
from __future__ import annotations

import hashlib
import re

ORGAN = "index"
SPINE_KIND = "index-context-envelope"
STATUSES = frozenset({
    "pass", "fail", "unverified", "warn", "needs-human", "not-applicable", "unknown",
})
_HEX = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = ("entry_id", "organ_id", "receipt_kind", "status", "payload_sha256",
           "summary", "payload_ref")


def _entry(entry_id: str, status: str, payload_sha256: str, summary: str, ref: str) -> dict:
    return {
        "entry_id": entry_id,
        "organ_id": ORGAN,
        "receipt_kind": SPINE_KIND,
        "status": status,
        "payload_sha256": payload_sha256,
        "summary": summary[:160],
        "payload_ref": ref,
    }


def envelope_entry(envelope: dict, *, entry_id: str = "index-envelope-1",
                   ref: str = "index://context-envelope") -> dict:
    """Map an index context-envelope output into an organ-bundle entry.

    The envelope is a JSON dict (schema project-telos.context-envelope/v1)
    produced by `index context --json` or the `index.context.envelope` MCP tool.
    """
    verification = envelope.get("verification_verdict", "UNVERIFIABLE")
    selection = envelope.get("selection", {})
    mode = selection.get("mode", "?") if isinstance(selection, dict) else "?"
    retained = selection.get("retained_names", []) if isinstance(selection, dict) else []
    repo_count = len(retained)

    status = "pass" if verification == "MATCH" else "warn" if verification else "unverified"

    # Use the envelope's own hash if present, else hash the canonical form
    sha = envelope.get("envelope_sha256", "")
    if not sha or not _HEX.match(sha):
        import json
        canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    summary = f"context-envelope: {repo_count} repos, mode={mode}, verdict={verification}"
    return _entry(entry_id, status, sha, summary, ref)


def map_entry(repo: str, *, n_repos: int = 1, map_sha: str = "",
              entry_id: str = "index-map-1",
              ref: str = "index://map") -> dict:
    """Map an index map result into an organ-bundle entry."""
    if not map_sha:
        map_sha = hashlib.sha256(repo.encode("utf-8")).hexdigest()
    summary = f"workspace map: {repo} ({n_repos} repos)"
    return _entry(entry_id, "pass", map_sha, summary, ref)


def validate_entry(entry: dict) -> bool:
    """Validate one organ-bundle entry shape. Returns True if well-formed."""
    if not isinstance(entry, dict):
        return False
    if set(entry.keys()) != set(_FIELDS):
        return False
    if entry["organ_id"] != ORGAN:
        return False
    if entry["receipt_kind"] != SPINE_KIND:
        return False
    if entry["status"] not in STATUSES:
        return False
    if not _HEX.match(entry.get("payload_sha256", "")):
        return False
    return True
