from __future__ import annotations

from workspace_repo_map.graph.edges import Edge, build_index, resolve_edges
from workspace_repo_map.graph.resolvers.base import RawEdge


def test_internal_edge_merges_signals_to_high_confidence():
    exposed = {"a": {"a-pkg"}, "b": {"b-pkg"}}
    index = build_index(exposed)
    raw = {"a": [
        RawEdge("b-pkg", "manifest", "pyproject.toml", None, "b-pkg"),
        RawEdge("b_pkg", "import", "a/x.py", 3, "import b_pkg"),
    ]}
    edges, warns = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1
    e = internal[0]
    assert (e.from_repo, e.to_repo) == ("a", "b")
    assert e.confidence == "high"
    assert len(e.signals) == 2
    assert all(e.signals)  # no empty


def test_external_edge_unresolved():
    index = build_index({"a": {"a-pkg"}})
    raw = {"a": [RawEdge("requests", "manifest", "pyproject.toml", None, "requests")]}
    edges, _ = resolve_edges(raw, index)
    assert len(edges) == 1
    assert edges[0].external is True and edges[0].to_repo is None


def test_self_edge_dropped():
    index = build_index({"a": {"a-pkg"}})
    raw = {"a": [RawEdge("a-pkg", "import", "a/x.py", 1, "import a_pkg")]}
    edges, _ = resolve_edges(raw, index)
    assert edges == []


def test_ambiguous_name_is_low_confidence_with_warning():
    index = build_index({"a": {"shared"}, "b": {"shared"}, "c": set()})
    raw = {"c": [RawEdge("shared", "manifest", "pyproject.toml", None, "shared")]}
    edges, warns = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert internal and internal[0].confidence == "low"
    assert any("ambiguous" in w for w in warns)


def test_no_edge_has_empty_signals():
    index = build_index({"a": {"a-pkg"}, "b": {"b-pkg"}})
    raw = {"a": [RawEdge("b-pkg", "manifest", "pyproject.toml", None, "b-pkg")]}
    edges, _ = resolve_edges(raw, index)
    assert all(len(e.signals) >= 1 for e in edges)
