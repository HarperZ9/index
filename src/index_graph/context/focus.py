"""Typed focus rejection receipts (index.focus-rejection/v1).

A free-form focus selector that resolves to no repo fails TYPED, following
the index.path-selection/v1 precedent: the receipt names the unresolved
selector, a reason code from a closed set, and a bounded candidate list,
so a host can recover (pick a candidate, widen the scope) instead of
parsing a bare error string.
"""
from __future__ import annotations

from collections.abc import Iterable

REJECTION_SCHEMA = "index.focus-rejection/v1"

# The closed set of rejection reason codes. A new code is added here,
# never invented at a call site.
REASON_CODES = frozenset({
    "unresolved-focus",   # the selector matches no repo in the workspace
    "empty-workspace",    # there are no repos to match against at all
})

CANDIDATE_LIMIT = 8


def focus_rejection(selector: str, names: Iterable[str],
                    limit: int = CANDIDATE_LIMIT) -> dict:
    """Build the typed rejection receipt for an unresolvable ``selector``.

    Candidates are bounded to ``limit``: case-insensitive near matches
    first, then the remaining repo names in sorted order. ``truncated``
    declares when the bound cut the list, and ``candidate_count`` always
    carries the full population, so the receipt never implies the shown
    candidates are all there is.
    """
    pool = sorted(set(names))
    lowered = selector.lower()
    near = [n for n in pool if lowered in n.lower() or n.lower() in lowered]
    rest = [n for n in pool if n not in near]
    candidates = (near + rest)[:max(limit, 0)]
    return {
        "schema": REJECTION_SCHEMA,
        "selector": selector,
        "reason_code": "empty-workspace" if not pool else "unresolved-focus",
        "candidates": candidates,
        "candidate_count": len(pool),
        "truncated": len(pool) > len(candidates),
    }


class FocusRejection(ValueError):
    """An unresolvable focus selector, carrying its typed receipt.

    Subclasses ValueError so existing callers that catch ValueError keep
    working; new callers read ``.receipt`` for the typed contract.
    """

    def __init__(self, receipt: dict):
        super().__init__(f"unknown focus repo: {receipt['selector']}")
        self.receipt = receipt


def resolve_focus(selector: str, names: Iterable[str]) -> str:
    """Return ``selector`` when it names a repo; raise FocusRejection otherwise."""
    pool = set(names)
    if selector in pool:
        return selector
    raise FocusRejection(focus_rejection(selector, pool))


def render_rejection(receipt: dict) -> str:
    """One human-readable line for the CLI faces; the JSON receipt is the contract."""
    line = f"focus rejected: {receipt['selector']!r} ({receipt['reason_code']})"
    if receipt["candidates"]:
        line += "; candidates: " + ", ".join(receipt["candidates"])
        hidden = receipt["candidate_count"] - len(receipt["candidates"])
        if receipt["truncated"] and hidden > 0:
            line += f" (+{hidden} more)"
    return line
