"""The README first screen answers what/who/problem/try-now in product
language: the single-repo wiki leads, the naming triple is visible, a
rendered demo is linked, and the operator-spine material sits below the
value demonstration."""
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"
FIRST_SCREEN_LINES = 60


def _text() -> str:
    return README.read_text(encoding="utf-8")


def _first_screen() -> str:
    return "\n".join(_text().splitlines()[:FIRST_SCREEN_LINES])


def test_first_screen_leads_with_the_single_repo_wiki():
    first = _first_screen()
    assert "pip install index-graph" in first
    assert "index wiki" in first
    assert first.index("index wiki") < first.index("index atlas")


def test_first_screen_states_the_naming_triple_on_one_line():
    lines = [ln for ln in _first_screen().splitlines()
             if "index-graph" in ln and "import index_graph" in ln]
    assert lines, "no single visible line documents install/run/import naming"


def test_first_screen_links_a_rendered_demo_artifact():
    first = _first_screen()
    assert "examples/wiki-demo.html" in first
    assert "examples/atlas-demo.html" in first


def test_operator_spine_material_sits_below_the_value_demonstration():
    text = _text()
    first = _first_screen()
    assert "Operator surface" not in first
    assert "operator-spine" not in first
    # moved below, not deleted
    assert "index status --json" in text
    assert text.index("index wiki") < text.index("Operator surface")
