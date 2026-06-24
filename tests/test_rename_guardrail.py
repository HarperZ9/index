import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _py_files():
    this = Path(__file__).resolve()
    return [p for p in list((ROOT / "src").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")) if p != this]


def test_no_stale_import_package_name():
    offenders = [str(p) for p in _py_files() if "workspace_repo_map" in p.read_text(encoding="utf-8")]
    assert not offenders, f"stale 'workspace_repo_map' import token in: {offenders}"


def test_package_imports_under_new_name():
    import index_graph  # must resolve
    import index_graph.viz  # the dashboard subpackage
    assert index_graph.__name__ == "index_graph"
