from index_graph.graph.edges import Edge
from index_graph.graph.cycles import find_cycles, cycle_edge_keys


def _e(a, b, external=False):
    return Edge(a, (None if external else b), b if external else b, external, "high", ())


def test_pure_dag_has_no_cycles():
    edges = [_e("a", "b"), _e("b", "c")]
    assert find_cycles(edges) == []


def test_two_node_cycle():
    edges = [_e("a", "b"), _e("b", "a")]
    assert find_cycles(edges) == [("a", "b")]


def test_three_node_cycle_sorted():
    edges = [_e("b", "c"), _e("c", "a"), _e("a", "b")]
    assert find_cycles(edges) == [("a", "b", "c")]


def test_self_loop_is_a_cycle():
    assert find_cycles([_e("a", "a")]) == [("a",)]


def test_two_disjoint_cycles_sorted():
    edges = [_e("a", "b"), _e("b", "a"), _e("y", "z"), _e("z", "y")]
    assert find_cycles(edges) == [("a", "b"), ("y", "z")]


def test_external_edges_never_form_cycles():
    edges = [_e("a", "ext", external=True), _e("ext", "a", external=True)]
    assert find_cycles(edges) == []


def test_determinism_under_shuffle():
    a = [_e("a", "b"), _e("b", "c"), _e("c", "a")]
    b = list(reversed(a))
    assert find_cycles(a) == find_cycles(b)


def test_cycle_edge_keys():
    edges = [_e("a", "b"), _e("b", "a"), _e("a", "x")]
    cycles = find_cycles(edges)
    assert cycle_edge_keys(edges, cycles) == {("a", "b"), ("b", "a")}
