import hashlib
import json
from pathlib import Path

import pytest

from index_graph.cli import main


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


@pytest.fixture
def workspace_with_external(tmp_path):
    # one tiny python repo depending on both a sibling lib AND an external package (requests)
    for name, deps_list in (("app", ["thelib", "requests"]), ("thelib", [])):
        d = tmp_path / name
        (d / "src").mkdir(parents=True)
        (d / ".git").mkdir()
        deps_str = ", ".join([f'"{dep}"' for dep in deps_list])
        (d / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\ndependencies = [{deps_str}]\n',
            encoding="utf-8"
        )
        if name == "app":
            (d / "src" / "main.py").write_text(
                "import thelib\nimport requests\n", encoding="utf-8"
            )
        else:
            (d / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
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
    for key, fname in (("svg", "graph.svg"), ("mermaid", "graph.mmd"), ("html", "graph.html")):
        assert manifest["renders"][key]["sha256"] == hashlib.sha256((out / fname).read_bytes()).hexdigest()


def test_unknown_focus_exits_2(workspace, tmp_path):
    rc = main(["viz", "--root", str(workspace), "--focus", "nope", "--out", str(tmp_path / "x.html")])
    assert rc == 2


def test_existing_commands_unaffected(workspace, tmp_path, capsys):
    rc = main(["graph", "--root", str(workspace), "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)  # still valid JSON


def test_version_is_0_4_0():
    from index_graph import __version__
    assert __version__ == "0.4.0"


def test_all_format_no_external_is_consistent(workspace_with_external, tmp_path):
    # Sanity check: without --no-external, "requests" should appear in the output
    out_default = tmp_path / "viz_default"
    rc = main(["viz", "--root", str(workspace_with_external), "--format", "all", "--out-dir", str(out_default)])
    assert rc == 0
    mmd_default = (out_default / "graph.mmd").read_text(encoding="utf-8")
    assert "requests" in mmd_default, "requests should appear in mermaid when --no-external is NOT used"

    # Real guard: with --no-external, "requests" must NOT appear in ANY output
    out_filtered = tmp_path / "viz_noext"
    rc = main(["viz", "--root", str(workspace_with_external), "--format", "all", "--no-external", "--out-dir", str(out_filtered)])
    assert rc == 0
    mmd_filtered = (out_filtered / "graph.mmd").read_text(encoding="utf-8")
    svg_filtered = (out_filtered / "graph.svg").read_text(encoding="utf-8")

    # Cross-format consistency: "requests" must not appear in either mermaid or svg
    assert "requests" not in mmd_filtered, "requests should NOT appear in mermaid with --no-external"
    assert "requests" not in svg_filtered, "requests should NOT appear in svg with --no-external"

    # Both artifacts must exist and be non-empty
    assert len(mmd_filtered) > 0
    assert len(svg_filtered) > 0
