"""Resolve RawEdges into evidence-carrying repo->repo Edges."""
from __future__ import annotations

from dataclasses import dataclass

from .resolvers.base import RawEdge, normalize_name


@dataclass(frozen=True)
class Signal:
    kind: str                 # "manifest" | "import"
    evidence_file: str
    evidence_line: int | None
    raw_spec: str


@dataclass(frozen=True)
class Edge:
    from_repo: str
    to_repo: str | None
    target_name: str
    external: bool
    confidence: str           # "high" | "moderate" | "low"
    signals: tuple[Signal, ...]


def build_index(exposed: dict[str, set[str]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for repo, names in exposed.items():
        for n in names:
            key = normalize_name(n)
            bucket = index.setdefault(key, [])
            if repo not in bucket:
                bucket.append(repo)
    return index


def _grade(signals: list[Signal], ambiguous: bool, target: str, short_len: int) -> str:
    if ambiguous or len(normalize_name(target)) <= short_len:
        return "low"
    kinds = {s.kind for s in signals}
    return "high" if {"manifest", "import"} <= kinds else "moderate"


def resolve_edges(repo_raw: dict[str, list[RawEdge]], index: dict[str, list[str]],
                  short_len: int = 2) -> tuple[list[Edge], list[str]]:
    warnings: list[str] = []
    # group RawEdges by (from_repo, resolved_target_or_external_name)
    grouped: dict[tuple[str, str | None, str], list[Signal]] = {}
    ambiguous_keys: set[tuple[str, str | None, str]] = set()
    for frm, raws in repo_raw.items():
        for r in raws:
            candidates = index.get(normalize_name(r.target_name), [])
            internal = [c for c in candidates if c != frm]
            sig = Signal(r.signal, r.evidence_file, r.evidence_line, r.raw_spec)
            if not candidates:
                key = (frm, None, normalize_name(r.target_name))  # external
            elif not internal:
                continue  # self-edge only -> drop
            else:
                to = sorted(internal)[0]
                key = (frm, to, normalize_name(r.target_name))
                if len(internal) > 1:
                    ambiguous_keys.add(key)
                    warnings.append(
                        f"ambiguous: {frm} -> {r.target_name!r} matches {sorted(internal)}")
            grouped.setdefault(key, []).append(sig)

    edges: list[Edge] = []
    for (frm, to, target), signals in grouped.items():
        external = to is None
        conf = "moderate" if external else _grade(
            signals, (frm, to, target) in ambiguous_keys, target, short_len)
        edges.append(Edge(frm, to, target, external, conf, tuple(signals)))
    edges.sort(key=lambda e: (e.from_repo, e.to_repo or "", e.target_name))
    return edges, warnings
