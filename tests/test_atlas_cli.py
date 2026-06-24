import json
from pathlib import Path

from index_graph.cli import main


def _workspace(root: Path):
    (root / "alpha").mkdir(); (root / "beta").mkdir(); (root / "docs").mkdir()
    (root / "alpha" / ".git").write_text("", encoding="utf-8")
    (root / "alpha" / "pyproject.toml").write_text('[project]\nname="alpha"\ndependencies=["beta"]\n', encoding="utf-8")
    (root / "alpha" / "a.py").write_text("import beta\n", encoding="utf-8")
    (root / "alpha" / "README.md").write_text("# Alpha\n\nUses [[Beta]].\n", encoding="utf-8")
    (root / "beta" / ".git").write_text("", encoding="utf-8")
    (root / "beta" / "pyproject.toml").write_text('[project]\nname="beta"\n', encoding="utf-8")
    (root / "docs" / "arch.md").write_text("# Architecture\n\nalpha and beta.\n", encoding="utf-8")


def test_atlas_html_writes_self_contained_two_layer_file(tmp_path):
    _workspace(tmp_path)
    out = tmp_path / "atlas.html"
    rc = main(["atlas", "--root", str(tmp_path), "--format", "html", "--out", str(out)])
    assert rc == 0
    html = out.read_text(encoding="utf-8")
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'data-name="alpha"' in html and 'data-doc="alpha/README.md"' in html
    assert "<link" not in html.lower() and "@import" not in html


def test_atlas_json_still_emits_engine_pack(tmp_path, capsys):
    _workspace(tmp_path)
    rc = main(["atlas", "--root", str(tmp_path), "--json"])
    assert rc == 0
    pack = json.loads(capsys.readouterr().out)
    assert "knowledge_edges" in pack and "docs" in pack
