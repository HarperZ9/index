# tests/test_viz_mermaid.py
import re

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
    assert re.search(r"^\s+class n_\w+ \w+;", out, re.MULTILINE)


def test_render_is_deterministic():
    assert render_mermaid(simple_pack()) == render_mermaid(simple_pack())


def test_distinct_names_get_distinct_ids():
    pack = {
        "repos": [
            {"name": "a-b", "salience": 1.0},
            {"name": "a_b", "salience": 1.0},
        ],
        "roles": {
            "a-b": ["hub"],
            "a_b": ["library"],
        },
        "relations": [],
    }
    out = render_mermaid(pack)
    # Both nodes must appear as declarations
    assert '["a-b"]' in out
    assert '["a_b"]' in out
    # Extract the id token before each '[' in declaration lines
    ids_found = re.findall(r'^\s+(n_\w+)\[', out, re.MULTILINE)
    assert len(ids_found) == 2, f"Expected 2 node declarations, got: {ids_found}"
    assert ids_found[0] != ids_found[1], f"Both nodes got the same id: {ids_found[0]}"


def test_empty_pack_renders_header_only():
    out = render_mermaid({})
    assert out.splitlines()[0].strip() == "flowchart TD"
    assert "-->" not in out
