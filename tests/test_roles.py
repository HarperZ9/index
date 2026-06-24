from __future__ import annotations

from index_graph.graph.edges import Edge, Signal
from index_graph.graph.roles import (derive_roles, salience_audit,
                                            structural_salience)


def _edge(a, b):
    return Edge(a, b, "x", False, "high", (Signal("import", "f", 1, "x"),))


def test_structural_salience_hub():
    edges = [_edge("a", "c"), _edge("b", "c")]
    sal = structural_salience(edges)
    assert sal["c"]["in_degree"] == 2 and sal["c"]["hub"] is True
    assert sal["a"]["out_degree"] == 1 and sal["a"]["hub"] is False


def test_derive_roles_hub_library_entrypoint_leaf():
    edges = [_edge("app", "lib"), _edge("util", "lib")]
    markers = {"app": {"entry", "published"}, "lib": {"published"}, "leafy": set()}
    roles = derive_roles({"app", "util", "lib", "leafy"}, edges, markers)
    assert "hub" in roles["lib"] and "library" in roles["lib"]
    assert "entrypoint" in roles["app"]
    assert "leaf" in roles["leafy"]


def test_salience_audit_flags_mismatches():
    sal = {"hubnode": {"in_degree": 3, "out_degree": 0, "hub": True},
           "shiny": {"in_degree": 0, "out_degree": 1, "hub": False}}
    marked = {"shiny": ["entry"]}
    warns = salience_audit(sal, marked)
    kinds = {w["kind"] for w in warns}
    assert "decorative-non-hub" in kinds and "unmarked-hub" in kinds
