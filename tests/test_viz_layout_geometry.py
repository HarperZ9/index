# tests/test_viz_layout_geometry.py
from workspace_repo_map.viz.layout import build_layout
from viz_fixtures import simple_pack, cyclic_pack


def _rects(layout):
    return [(n.x, n.y, n.w, n.h) for n in layout.nodes]


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def test_no_two_node_boxes_overlap():
    layout = build_layout(simple_pack())
    rects = _rects(layout)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not _overlap(rects[i], rects[j])


def test_lower_layers_sit_below_higher_layers():
    layout = build_layout(simple_pack())
    web = next(n for n in layout.nodes if n.name == "web")
    lib = next(n for n in layout.nodes if n.name == "lib")
    assert web.y < lib.y


def test_each_edge_has_four_control_points_within_canvas():
    layout = build_layout(simple_pack())
    assert layout.width > 0 and layout.height > 0
    for e in layout.edges:
        assert len(e.points) == 4
        for px, py in e.points:
            assert 0 <= px <= layout.width
            assert -1 <= py <= layout.height + 1


def test_cycle_produces_exactly_one_back_edge():
    layout = build_layout(cyclic_pack())
    backs = [e for e in layout.edges if e.back_edge]
    assert len(backs) == 1


def test_layout_is_byte_deterministic():
    a = build_layout(simple_pack())
    b = build_layout(simple_pack())
    assert a == b  # frozen dataclasses compare by value


def test_back_edge_control_points_stay_within_canvas():
    layout = build_layout(cyclic_pack())
    assert any(e.back_edge for e in layout.edges)
    for e in layout.edges:
        for px, py in e.points:
            assert 0 <= px <= layout.width
            assert -1 <= py <= layout.height + 1


def test_empty_graph_renders_a_valid_empty_canvas():
    empty = {"roles": {}, "relations": [], "salience": {},
             "salience_audit": [], "repos": [], "warnings": []}
    layout = build_layout(empty)
    assert layout.nodes == ()
    assert layout.edges == ()
    assert layout.width > 0 and layout.height > 0  # drawable empty canvas, not a crash
