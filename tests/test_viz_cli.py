import json
from pathlib import Path

import pytest

from workspace_repo_map.cli import main


@pytest.fixture
def workspace(tmp_path):
    # one tiny python repo depending on a sibling lib (mirrors tests/fixtures convention)
    for name, dep in (("app", "thelib"), ("thelib", None)):
        d = tmp_path / name
        (d / "src").mkdir(parents=True)
        (d / ".git").mkdir()
        deps = f'dependencies = ["{dep}"]' if dep else "dependencies = []"
        (d / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\n{deps}\n', encoding="utf-8"
        )
        (d / "src" / "main.py").write_text(
            ("import thelib\n" if dep else "x = 1\n"), encoding="utf-8"
        )
    return tmp_path


def test_viz_html_writes_self_contained_file(workspace, tmp_path):
    out = tmp_path / "graph.html"
    rc = main(["viz", "--root", str(workspace), "--format", "html", "--out", str(out)])
    assert rc == 0
    doc = out.read_text(encoding="utf-8")
    assert doc.lstrip().lower().startswith("<!doctype html>")
    assert "https://" not in doc.replace("http://www.w3.org/2000/svg", "")


def test_viz_all_emits_every_artifact_and_manifest(workspace, tmp_path):
    out = tmp_path / "viz"
    rc = main(["viz", "--root", str(workspace), "--format", "all", "--out-dir", str(out)])
    assert rc == 0
    for f in ("graph.mmd", "graph.svg", "graph.html", "context.json", "context-manifest.json"):
        assert (out / f).exists()
    manifest = json.loads((out / "context-manifest.json").read_text(encoding="utf-8"))
    assert manifest["renders"]["svg"]["path"] == "graph.svg"


def test_unknown_focus_exits_2(workspace, tmp_path):
    rc = main(["viz", "--root", str(workspace), "--focus", "nope", "--out", str(tmp_path / "x.html")])
    assert rc == 2


def test_existing_commands_unaffected(workspace, tmp_path, capsys):
    rc = main(["graph", "--root", str(workspace), "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)  # still valid JSON


def test_version_is_0_4_0():
    from workspace_repo_map import __version__
    assert __version__ == "0.4.0"
