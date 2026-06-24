# tests/test_viz_mermaid.py
from workspace_repo_map.viz.mermaid import render_mermaid
from viz_fixtures import simple_pack


def test_starts_with_flowchart_td():
    assert render_mermaid(simple_pack()).splitlines()[0].strip() == "flowchart TD"


def test_every_edge_carries_confidence_and_signal_kind():
    out = render_mermaid(simple_pack())
    assert "-->|high (import)|" in out  # confidence grade + the witnessed signal kind
    assert out.count("-->") == 4  # 3 internal + 1 external edge


def test_external_dependency_uses_a_distinct_shape():
    out = render_mermaid(simple_pack())
    assert '(("requests"))' in out


def test_role_classdefs_are_emitted_and_assigned():
    out = render_mermaid(simple_pack())
    assert "classDef hub" in out
    assert "class " in out  # node-to-class assignment lines


def test_render_is_deterministic():
    assert render_mermaid(simple_pack()) == render_mermaid(simple_pack())
