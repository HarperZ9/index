import xml.dom.minidom as minidom

from index_graph.viz.atlas_layout import build_atlas_layout
from index_graph.viz.atlas_svg import render_atlas_svg
from viz_fixtures import simple_atlas


def _svg():
    pack, _ = simple_atlas()
    return render_atlas_svg(build_atlas_layout(pack))


def test_svg_is_well_formed_and_has_viewport():
    svg = _svg()
    minidom.parseString(svg)
    assert svg.lstrip().startswith("<svg")
    assert '<g id="viewport">' in svg


def test_repo_and_doc_nodes_present():
    svg = _svg()
    assert 'data-name="app"' in svg and 'data-name="lib"' in svg     # repos (reused renderer)
    assert 'data-doc="app/README.md"' in svg                          # doc node
    assert 'class="docnode' in svg


def test_knowledge_edge_classes_present_and_mentions_is_dim():
    svg = _svg()
    assert "kedge-describes" in svg
    assert "kedge-links-to" in svg
    assert "kedge-mentions" in svg
    assert ".kedge-mentions{" in svg and "opacity:.35" in svg          # mentions dimmest in style


def test_hostile_doc_title_stays_well_formed():
    pack, _ = simple_atlas()
    pack["docs"].append({"id": "x.md", "title": 'a"<&b', "dir": ""})
    svg = render_atlas_svg(build_atlas_layout(pack))
    minidom.parseString(svg)                                          # must not raise


def test_render_is_deterministic():
    assert _svg() == _svg()
