from index_graph.context.pack import closure, preservation
from index_graph.graph.edges import Edge


def _edge(a, b):
    return Edge(a, b, b, False, "high", ())


def test_closure_is_hop_bounded():
    edges = [_edge("a", "b"), _edge("b", "c"), _edge("c", "d")]
    assert closure(edges, "a", hops=1) == {"a", "b"}
    assert closure(edges, "a", hops=2) == {"a", "b", "c"}
    assert closure(edges, "a") == {"a", "b", "c", "d"}  # full connected component


def test_preservation_marks_the_boundary():
    edges = [_edge("a", "b"), _edge("b", "c"), _edge("c", "d")]
    keep = closure(edges, "a", hops=1)  # {a, b}
    p = preservation(edges, keep, "a", 1)
    assert p["focus"] == ["a"]
    assert p["hops"] == 1
    assert p["kept_nodes"] == 2
    assert "c" in p["boundary"]["dropped_nodes"]
    assert "b -> c" in p["boundary"]["dropped_edges"]
    # an edge fully inside keep is not a boundary edge
    assert "a -> b" not in p["boundary"]["dropped_edges"]


def test_full_focus_drops_nothing():
    edges = [_edge("a", "b"), _edge("b", "c")]
    keep = closure(edges, "a")  # whole component
    p = preservation(edges, keep, "a", None)
    assert p["boundary"]["dropped_edges"] == []
    assert p["boundary"]["dropped_nodes"] == []
