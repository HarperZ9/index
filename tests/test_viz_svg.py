import json
import xml.dom.minidom as minidom

from index_graph.viz.layout import build_layout
from index_graph.viz.svg import render_svg
from viz_fixtures import simple_pack


def test_svg_is_well_formed_xml():
    svg = render_svg(build_layout(simple_pack()))
    minidom.parseString(svg)  # raises on malformed XML
    assert svg.lstrip().startswith("<svg")


def test_every_node_and_edge_is_present():
    layout = build_layout(simple_pack())
    svg = render_svg(layout)
    for n in layout.nodes:
        assert f'data-name="{n.name}"' in svg
    # 4 relations -> 4 edge paths
    assert svg.count('class="edge') == len(layout.edges)


def test_confidence_styling_class_is_applied():
    svg = render_svg(build_layout(simple_pack()))
    assert 'class="edge edge-high"' in svg  # a rendered high edge, not merely the CSS class
    assert "edge edge-moderate" in svg       # the moderate (external) edge path


def test_edge_carries_its_witnessed_signals():
    svg = render_svg(build_layout(simple_pack()))
    assert "data-signals=" in svg
    assert "import" in svg  # the signal kind from the fixture travels into the markup


def test_render_is_deterministic():
    a = render_svg(build_layout(simple_pack()))
    b = render_svg(build_layout(simple_pack()))
    assert a == b  # pure function of input: no wall-clock, no host data
    for clock_marker in ("GMT", "UTC", "datetime"):  # no date library leaked a timestamp
        assert clock_marker not in a


def test_special_chars_in_repo_name_stay_well_formed():
    name = 'a"<&b'
    pack = {
        "roles": {name: ["hub"]},
        "relations": [],
        "salience": {name: {"in_degree": 0, "out_degree": 0, "hub": True}},
        "salience_audit": [],
        "repos": [{"name": name, "ecosystems": ["python"], "description": "x", "markers": []}],
        "warnings": [],
    }
    svg = render_svg(build_layout(pack))
    minidom.parseString(svg)  # must not raise


def test_cycle_edge_and_node_get_cycle_class():
    from index_graph.viz.layout import build_layout
    from index_graph.viz.svg import render_svg
    pack = {
        "repos": [{"name": "a"}, {"name": "b"}],
        "roles": {"a": ["hub"], "b": ["hub"]},
        "salience": {"a": {"in_degree": 1, "out_degree": 1},
                     "b": {"in_degree": 1, "out_degree": 1}},
        "cycles": [["a", "b"]],
        "relations": [
            {"from": "a", "to": "b", "confidence": "high", "external": False,
             "in_cycle": True, "signals": []},
            {"from": "b", "to": "a", "confidence": "high", "external": False,
             "in_cycle": True, "signals": []},
        ],
    }
    svg = render_svg(build_layout(pack))
    assert "edge-cycle" in svg
    assert "cycle" in svg  # node class
