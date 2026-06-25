"""Diff two snapshots into a DriftReport with a MATCH/DRIFT verdict."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriftReport:
    repos_added: tuple[str, ...]
    repos_removed: tuple[str, ...]
    edges_added: tuple[str, ...]
    edges_removed: tuple[str, ...]
    cycles_introduced: tuple[tuple[str, ...], ...]
    cycles_cleared: tuple[tuple[str, ...], ...]
    roles_changed: tuple[tuple[str, str, str], ...]

    @property
    def verdict(self) -> str:
        changed = any([
            self.repos_added, self.repos_removed, self.edges_added,
            self.edges_removed, self.cycles_introduced, self.cycles_cleared,
            self.roles_changed,
        ])
        return "DRIFT" if changed else "MATCH"

    def to_json(self) -> dict:
        return {
            "verdict": self.verdict,
            "repos_added": list(self.repos_added),
            "repos_removed": list(self.repos_removed),
            "edges_added": list(self.edges_added),
            "edges_removed": list(self.edges_removed),
            "cycles_introduced": [list(c) for c in self.cycles_introduced],
            "cycles_cleared": [list(c) for c in self.cycles_cleared],
            "roles_changed": [list(t) for t in self.roles_changed],
        }


def _cycle_set(snap: dict) -> set[tuple[str, ...]]:
    return {tuple(c) for c in snap.get("cycles", [])}


def diff_snapshots(old: dict, new: dict) -> DriftReport:
    o_repos, n_repos = set(old.get("repos", [])), set(new.get("repos", []))
    o_edges, n_edges = set(old.get("edges", [])), set(new.get("edges", []))
    o_cyc, n_cyc = _cycle_set(old), _cycle_set(new)
    o_roles, n_roles = old.get("roles", {}), new.get("roles", {})
    roles_changed: list[tuple[str, str, str]] = []
    for repo in sorted(set(o_roles) & set(n_roles)):
        a, b = o_roles.get(repo, []), n_roles.get(repo, [])
        if a != b:
            roles_changed.append((repo, ",".join(a), ",".join(b)))
    return DriftReport(
        repos_added=tuple(sorted(n_repos - o_repos)),
        repos_removed=tuple(sorted(o_repos - n_repos)),
        edges_added=tuple(sorted(n_edges - o_edges)),
        edges_removed=tuple(sorted(o_edges - n_edges)),
        cycles_introduced=tuple(sorted(n_cyc - o_cyc)),
        cycles_cleared=tuple(sorted(o_cyc - n_cyc)),
        roles_changed=tuple(roles_changed),
    )
