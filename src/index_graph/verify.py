"""Ground a structural claim against the verified graph: MATCH / REFUTED / UNVERIFIABLE.

The deterministic anti-hallucination oracle. An agent asserts a dependency or an
existence claim about the code; index confirms or refutes it from the real graph with
file:line evidence, instead of the agent trusting its own memory. This artifact has its
own honest triad (a false claim is REFUTED, not DRIFT) and is re-checkable: a consumer
re-runs `recheck` and recomputes the hash rather than trusting the verdict.
"""
from __future__ import annotations

from .certify import canonical_sha


def _evidence(rel: dict) -> str | None:
    sigs = rel.get("signals") or []
    if not sigs:
        return None
    s = sigs[0]
    f = s.get("file")
    if not f:
        return None
    line = s.get("line")
    return f"{f}:{line}" if line is not None else f


def _names(pack: dict) -> set[str]:
    names = set(pack.get("roles", {}).keys())
    for r in pack.get("relations", []):
        if r.get("from"):
            names.add(r["from"])
        if r.get("to"):
            names.add(r["to"])
    return names


def verify_claim(pack: dict, claim: dict) -> dict:
    """Return {verdict, evidence, detail} for a claim against the pack."""
    kind = claim.get("kind")
    names = _names(pack)

    if kind == "exists":
        name = claim.get("name")
        if name in names:
            return {"verdict": "MATCH", "evidence": None,
                    "detail": f"{name} is a repo in the workspace"}
        return {"verdict": "REFUTED", "evidence": None,
                "detail": f"{name} is not a repo in the workspace"}

    if kind == "depends":
        frm, to = claim.get("from"), claim.get("to")
        if frm not in names or to not in names:
            missing = frm if frm not in names else to
            return {"verdict": "UNVERIFIABLE", "evidence": None,
                    "detail": f"{missing} is not a repo in the workspace"}
        for r in pack.get("relations", []):
            if not r.get("external") and r.get("from") == frm and r.get("to") == to:
                return {"verdict": "MATCH", "evidence": _evidence(r),
                        "detail": f"{frm} depends on {to}"}
        return {"verdict": "REFUTED", "evidence": None,
                "detail": f"no dependency {frm} -> {to} in the graph"}

    return {"verdict": "UNVERIFIABLE", "evidence": None, "detail": "unknown claim kind"}


def build_verification(pack: dict, claim: dict, *, tool_version: str, recheck: str) -> dict:
    result = verify_claim(pack, claim)
    return {
        "schema": "index.verification/1",
        "tool_version": tool_version,
        "claim": claim,
        "verdict": result["verdict"],
        "evidence": result["evidence"],
        "detail": result["detail"],
        "content_sha256": canonical_sha(pack),
        "recheck": recheck,
    }
