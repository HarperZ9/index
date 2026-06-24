from index_graph.viz.svg import render_svg
from index_graph.viz.mermaid import render_mermaid
from index_graph.viz.layout import build_layout
from index_graph.viz.charts import render_charts
from index_graph.viz.html import render_html
from viz_fixtures import simple_pack

# words that would imply interpretation rather than reporting
BANNED = ("keystone", "critical", "important", "should", "recommend", "best", "worst", "elegant")


import re as _re


def _strip_style(html: str) -> str:
    """Remove <style>...</style> blocks before editorial scanning (CSS uses !important etc.)."""
    return _re.sub(r"<style[^>]*>.*?</style>", "", html, flags=_re.DOTALL)


def test_renderers_do_not_editorialize():
    pack = simple_pack()
    layout = build_layout(pack)
    charts = render_charts(pack)
    charts_combined = " ".join(charts.values())
    html_raw = render_html(pack, svg=render_svg(layout), charts=charts)
    html_out = _strip_style(html_raw)
    outputs = [render_mermaid(pack), render_svg(layout), charts_combined, html_out]
    assert all(out.strip() for out in outputs), "a renderer produced empty output — editorial check would be vacuous"
    for out in outputs:
        low = out.lower()
        for word in BANNED:
            assert word not in low, f"editorializing word {word!r} leaked into output"
