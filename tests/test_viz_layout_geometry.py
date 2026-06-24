# tests/test_viz_layout_geometry.py
from index_graph.viz.layout import build_layout
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


def test_dangling_edge_is_excluded_so_every_edge_has_four_points():
    # A pack with two real repos and one relation whose 'from' is NOT in repos.
    pack = {
        "repos": [
            {"name": "api"},
            {"name": "lib"},
        ],
        "roles": {
            "api": ["entrypoint"],
            "lib": ["library"],
        },
        "salience": {
            "api": {"in_degree": 0, "out_degree": 1, "hub": False},
            "lib": {"in_degree": 1, "out_degree": 0, "hub": False},
        },
        "relations": [
            # valid edge
            {"from": "api", "to": "lib", "confidence": "high"},
            # dangling source — "ghost" is not in repos
            {"from": "ghost", "to": "lib", "confidence": "low"},
        ],
        "warnings": [],
        "salience_audit": [],
    }
    layout = build_layout(pack, include_external=False)
    from_repos = {e.from_repo for e in layout.edges}
    assert "ghost" not in from_repos, "dangling-source edge must be excluded"
    assert all(len(e.points) == 4 for e in layout.edges), (
        "every surviving edge must have exactly 4 control points"
    )


def test_empty_graph_renders_a_valid_empty_canvas():
    empty = {"roles": {}, "relations": [], "salience": {},
             "salience_audit": [], "repos": [], "warnings": []}
    layout = build_layout(empty)
    assert layout.nodes == ()
    assert layout.edges == ()
    assert layout.width > 0 and layout.height > 0  # drawable empty canvas, not a crash
