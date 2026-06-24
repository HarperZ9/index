"""Topology-derived structural roles + salience faithfulness (ported)."""
from __future__ import annotations

from .edges import Edge


def structural_salience(edges: list[Edge]) -> dict[str, dict]:
    indeg: dict[str, int] = {}
    outdeg: dict[str, int] = {}
    for e in edges:
        if e.external or e.to_repo is None:
            continue
        outdeg[e.from_repo] = outdeg.get(e.from_repo, 0) + 1
        indeg[e.to_repo] = indeg.get(e.to_repo, 0) + 1
    nodes = set(indeg) | set(outdeg)
    max_in = max(indeg.values(), default=0)
    out: dict[str, dict] = {}
    for n in sorted(nodes):
        i, o = indeg.get(n, 0), outdeg.get(n, 0)
        out[n] = {"in_degree": i, "out_degree": o, "hub": i == max_in and i >= 2}
    return out


def derive_roles(repo_names: set[str], edges: list[Edge],
                 markers: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
    sal = structural_salience(edges)
    max_out = max((s["out_degree"] for s in sal.values()), default=0)
    roles: dict[str, list[str]] = {}
    for name in sorted(repo_names):
        s = sal.get(name, {"in_degree": 0, "out_degree": 0, "hub": False})
        mk = markers.get(name, set())
        rs: list[str] = []
        if "entry" in mk:
            rs.append("entrypoint")
        if "published" in mk and s["in_degree"] >= 1 and "entry" not in mk:
            rs.append("library")
        if s["hub"]:
            rs.append("hub")
        if s["out_degree"] == max_out and s["out_degree"] >= 3:
            rs.append("orchestrator")
        if s["in_degree"] == 0 and s["out_degree"] == 0 and name in markers:
            rs.append("leaf")
        if name not in markers:
            rs.append("isolated")
        roles[name] = tuple(rs)
    return roles


def salience_audit(salience: dict[str, dict], marked: dict[str, list[str]]) -> list[dict]:
    hubs = sorted(n for n, s in salience.items() if s["hub"])
    warns: list[dict] = []
    for name, mk in sorted(marked.items()):
        if name not in hubs:
            warns.append({"kind": "decorative-non-hub", "node": name, "markers": mk,
                          "in_degree": salience.get(name, {}).get("in_degree", 0),
                          "hubs": hubs,
                          "note": "marked node is not the structural hub; a render must not let "
                                  "its marker outshine the hub(s)"})
    for h in hubs:
        if h not in marked:
            warns.append({"kind": "unmarked-hub", "node": h,
                          "in_degree": salience.get(h, {}).get("in_degree", 0),
                          "note": "structural convergence hub carries no marker; a faithful render "
                                  "should make it central"})
    return warns
