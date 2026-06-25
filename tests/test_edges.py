from __future__ import annotations

from index_graph.graph.edges import Edge, build_index, resolve_edges
from index_graph.graph.resolvers.base import RawEdge


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


def test_index_dedups_same_repo_multiple_names():
    # A repo exposing its dist name AND package dir (both normalize equal)
    # should produce only one entry per key, not two.
    index = build_index({"lib": {"lib-name", "lib_name"}})
    assert index["lib-name"] == ["lib"]  # not ["lib", "lib"]


def test_double_exposed_target_is_high_confidence_not_ambiguous():
    # lib exposes {"lib-pkg", "lib_pkg"} — both normalize to "lib-pkg".
    # Before the fix, build_index produced ["lib", "lib"], so resolve_edges
    # saw len(internal) == 2 and falsely graded the edge as low/ambiguous.
    index = build_index({"app": {"app"}, "lib": {"lib-pkg", "lib_pkg"}})
    raw = {
        "app": [
            RawEdge("lib-pkg", "manifest", "pyproject.toml", None, "lib-pkg"),
            RawEdge("lib_pkg", "import", "app/main.py", 5, "import lib_pkg"),
        ]
    }
    edges, warns = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1
    e = internal[0]
    assert (e.from_repo, e.to_repo) == ("app", "lib")
    assert e.confidence == "high"
    assert not any("ambiguous" in w for w in warns)


def test_path_prefix_fallback_resolves_import_to_module():
    # Go-style: module "github.com/org/lib"; an import of a sub-package resolves to it,
    # and merges with the go.mod require into one high-confidence edge.
    index = build_index({"app": {"github.com/org/app"}, "lib": {"github.com/org/lib"}})
    raw = {"app": [
        RawEdge("github.com/org/lib", "manifest", "go.mod", None, "require github.com/org/lib v1"),
        RawEdge("github.com/org/lib/pkg/sub", "import", "app/main.go", 7, 'import "github.com/org/lib/pkg/sub"'),
    ]}
    edges, _ = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1
    e = internal[0]
    assert (e.from_repo, e.to_repo) == ("app", "lib")
    assert e.confidence == "high"                       # manifest + import agree
    assert e.target_name == "github.com/org/lib"        # canonical module, not the import path


def test_prefix_fallback_requires_segment_alignment():
    # "github.com/org/lib" must NOT match "github.com/org/libextra" (not a path prefix).
    index = build_index({"lib": {"github.com/org/lib"}})
    raw = {"app": [RawEdge("github.com/org/libextra", "import", "app/main.go", 1, "x")]}
    edges, _ = resolve_edges(raw, index)
    assert all(e.external for e in edges)               # no false prefix match


def test_exact_match_preferred_over_prefix():
    index = build_index({"lib": {"github.com/org/lib"}})
    raw = {"app": [RawEdge("github.com/org/lib", "import", "app/main.go", 1, "x")]}
    edges, _ = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1 and internal[0].to_repo == "lib"


def test_prefix_fallback_does_not_touch_slashless_names():
    # plain names (Python/JS) never enter the prefix path; behavior is identical.
    index = build_index({"a": {"a-pkg"}, "b": {"b-pkg"}})
    raw = {"a": [RawEdge("b-pkg", "manifest", "pyproject.toml", None, "b-pkg")]}
    edges, _ = resolve_edges(raw, index)
    internal = [e for e in edges if not e.external]
    assert len(internal) == 1 and internal[0].to_repo == "b"
