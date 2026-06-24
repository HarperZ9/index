from __future__ import annotations

import inspect
from pathlib import Path

from index_graph.context import pack
from index_graph.context.pack import (closure, focus_subgraph, render_text,
                                             to_json)
from index_graph.graph.build import build_graph

FIX = Path(__file__).parent / "fixtures"


def _graph():
    return build_graph({"py-app": FIX / "py-app", "py-lib": FIX / "py-lib"})


def test_render_text_has_three_sections_and_evidence():
    text = render_text(_graph(), "test")
    assert "## Roles" in text and "## Relations" in text and "## Inventory" in text
    assert "py-app -> py-lib" in text


def test_to_json_carries_salience_and_audit():
    data = to_json(_graph())
    assert "salience" in data and "salience_audit" in data
    assert "relations" in data and "roles" in data
    internal = [r for r in data["relations"] if not r["external"]]
    assert internal, "expected at least one internal relation"
    sig = internal[0]["signals"][0]
    assert sig["file"] and sig["kind"] in {"manifest", "import"}
    assert "line" in sig and "raw" in sig


def test_closure_is_bidirectional_and_cycle_safe():
    g = _graph()
    keep = closure(list(g.edges), "py-lib")
    assert "py-app" in keep and "py-lib" in keep  # reached upstream
    sub = focus_subgraph(g, keep)
    assert {n.name for n in sub.repos} == keep


def test_no_editorializing_no_banned_phrases_in_source():
    src = inspect.getsource(pack)
    banned = ["keystone", "the heart of", "is the most important", "clearly the",
              "obviously", "the best"]
    assert not [b for b in banned if b in src.lower()]


def test_pack_exposes_cycles_and_in_cycle():
    from index_graph.graph.edges import Edge
    from index_graph.graph.build import DependencyGraph, RepoNode
    from index_graph.context.pack import to_json

    def node(n):
        return RepoNode(n, f"/x/{n}", (), frozenset(), "d", frozenset())

    def edge(a, b):
        return Edge(a, b, b, False, "high", ())

    g = DependencyGraph(
        (node("a"), node("b")),
        (edge("a", "b"), edge("b", "a")),
        {"a": ("hub",), "b": ("hub",)}, ())
    pack = to_json(g)
    assert pack["cycles"] == [["a", "b"]]
    assert all(r["in_cycle"] for r in pack["relations"])
