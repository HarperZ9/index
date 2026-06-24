import re

from index_graph.viz.layout import build_layout
from index_graph.viz.svg import render_svg
from index_graph.viz.charts import render_charts
from index_graph.viz.html import render_html
from viz_fixtures import simple_pack


def _doc(pack):
    return render_html(pack, svg=render_svg(build_layout(pack)), charts=render_charts(pack))


def test_is_a_complete_html_document():
    doc = _doc(simple_pack())
    assert doc.lstrip().lower().startswith("<!doctype html>")
    assert "</html>" in doc


def test_embeds_data_svg_and_charts():
    doc = _doc(simple_pack())
    assert "const DATA =" in doc
    assert "<svg" in doc
    assert 'class="chart"' in doc


def test_is_self_contained_no_external_urls():
    doc = _doc(simple_pack())
    urls = re.findall(r"https?://[^\s\"')]+", doc)
    # the ONLY permitted http(s) token is the SVG XML namespace
    assert set(urls) <= {"http://www.w3.org/2000/svg"}
    assert "cdn" not in doc.lower()
    assert "<link" not in doc.lower()
    assert "@import" not in doc
    assert re.search(r'''(?:href|src|url\()\s*["']?//''', doc) is None


def test_render_is_deterministic():
    assert _doc(simple_pack()) == _doc(simple_pack())


def test_script_breakout_name_is_neutralized():
    bad_name = "x</script>y"
    pack = {
        "repos": [{"name": bad_name}],
        "roles": {bad_name: ["service"]},
        "salience": {bad_name: {"in_degree": 0, "out_degree": 0}},
        "relations": [],
    }
    doc = render_html(pack, svg=render_svg(build_layout(pack)), charts=render_charts(pack))
    assert doc.count("</script>") == 1


def test_salience_audit_panel_renders_entries():
    pack = simple_pack()
    pack["salience_audit"] = [
        {
            "kind": "decorative-non-hub",
            "node": "web",
            "markers": ["entry"],
            "in_degree": 0,
            "hubs": [],
            "note": "marked node is not the structural hub",
        }
    ]
    doc = render_html(pack, svg=render_svg(build_layout(pack)), charts=render_charts(pack))
    assert "salience audit" in doc
    assert "web" in doc
    assert "marked node is not the structural hub" in doc
    # self-containment still holds
    import re
    urls = re.findall(r"https?://[^\s\"')]+", doc)
    assert set(urls) <= {"http://www.w3.org/2000/svg"}


def test_salience_audit_panel_escapes_hostile_values():
    pack = simple_pack()
    pack["salience_audit"] = [
        {
            "kind": "decorative-non-hub",
            "node": "a<script>x",
            "markers": [],
            "in_degree": 0,
            "hubs": [],
            "note": 'b<&"c',
        }
    ]
    doc = render_html(pack, svg=render_svg(build_layout(pack)), charts=render_charts(pack))
    # The audit panel must escape HTML, so no unescaped <script> should appear
    assert doc.count("</script>") == 1, "only the real closing script tag should exist"
    # The escaped form should be present instead
    assert "&lt;script&gt;" in doc, "hostile node name should be escaped"
    assert "&lt;" in doc, "hostile characters in note should be escaped"


def test_edge_tooltip_and_neighborhood_wiring_present():
    doc = _doc(simple_pack())
    assert "function edgeTip" in doc
    assert "function highlight" in doc
    assert "data-signals" in doc  # edges carry evidence the tooltip reads
    assert "'tip'" in doc         # the tooltip element is created in the embedded JS


def test_legend_present_with_roles_and_confidence_and_cycle():
    doc = _doc(simple_pack())
    assert 'class="legend"' in doc
    assert "high" in doc and "moderate" in doc  # confidence styles labelled
    assert "cycle" in doc                       # cycle marker explained
    assert "library" in doc                     # a role label
