import re

from index_graph.knowledge.docs import Doc
from index_graph.viz.atlas_layout import build_atlas_layout
from index_graph.viz.atlas_svg import render_atlas_svg
from index_graph.viz.atlas_html import render_atlas_html
from viz_fixtures import simple_atlas


def _doc(pack, docs):
    svg = render_atlas_svg(build_atlas_layout(pack))
    return render_atlas_html(pack, docs, svg=svg)


def test_is_a_complete_self_contained_document():
    doc = _doc(*simple_atlas())
    assert doc.lstrip().lower().startswith("<!doctype html>")
    assert "</html>" in doc and "const DATA =" in doc and "<svg" in doc


def test_no_external_resource_loads():
    # content links (<a href="http">) are allowed; resource-load vectors are not.
    doc = _doc(*simple_atlas())
    assert "<link" not in doc.lower()
    assert "@import" not in doc
    assert "cdn" not in doc.lower()
    assert re.search(r'src\s*=\s*["\']?(?:https?:)?//', doc) is None
    assert re.search(r'url\(\s*["\']?https?:', doc) is None
    assert "<script src" not in doc.lower()


def test_doc_markdown_is_rendered_into_data():
    doc = _doc(*simple_atlas())
    assert "doc_html" in doc
    # rendered HTML lives inside DATA, where '<' is <-escaped against script-breakout,
    # so assert on markers that survive that escaping:
    assert "data-atlas-target" in doc                 # app/README's [[lib]] became a wiki span (server-rendered)
    assert "\\u003ch1>App" in doc                      # the rendered <h1>App</h1>, '<' escaped to <


def test_backlinks_index_present():
    doc = _doc(*simple_atlas())
    assert "backlinks" in doc


def test_hostile_doc_body_cannot_break_out():
    pack, _ = simple_atlas()
    hostile = [
        Doc("app/README.md", "App", "# Pwn\n\n<script>alert(1)</script> and `</script>`", (), "app"),
        Doc("docs/arch.md", "Architecture", "x", (), "docs"),
        Doc("lib/README.md", "Lib", "y", (), "lib"),
    ]
    doc = render_atlas_html(pack, hostile, svg=render_atlas_svg(build_atlas_layout(pack)))
    assert doc.count("</script>") == 1                 # only the real closing tag


def test_wikilink_navigation_is_wired():
    doc = _doc(*simple_atlas())
    assert "data-atlas-target" in doc
    assert "function detailDoc" in doc
    assert "wikilink" in doc


def test_render_is_deterministic():
    assert _doc(*simple_atlas()) == _doc(*simple_atlas())
