from workspace_repo_map.viz.svg import render_svg
from workspace_repo_map.viz.mermaid import render_mermaid
from workspace_repo_map.viz.layout import build_layout
from viz_fixtures import simple_pack

# words that would imply interpretation rather than reporting
BANNED = ("keystone", "critical", "important", "should", "recommend", "best", "worst", "elegant")


def test_renderers_do_not_editorialize():
    pack = simple_pack()
    outputs = [render_mermaid(pack), render_svg(build_layout(pack))]
    assert all(out.strip() for out in outputs), "a renderer produced empty output — editorial check would be vacuous"
    for out in outputs:
        low = out.lower()
        for word in BANNED:
            assert word not in low, f"editorializing word {word!r} leaked into output"
