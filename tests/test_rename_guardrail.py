from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _py_files():
    this = Path(__file__).resolve()
    roots = [ROOT / "src", ROOT / "tests", ROOT / "scripts"]
    files = [p for root in roots for p in root.rglob("*.py")]
    return [p for p in files if p != this]


def test_no_stale_import_package_name():
    offenders = [str(p) for p in _py_files() if "workspace_repo_map" in p.read_text(encoding="utf-8")]
    assert not offenders, f"stale 'workspace_repo_map' import token in: {offenders}"


def test_package_imports_under_new_name():
    import index_graph  # must resolve
    import index_graph.viz  # the dashboard subpackage
    assert index_graph.__name__ == "index_graph"


def test_no_stale_brand_string_in_code():
    offenders = [str(p) for p in _py_files() if "workspace-repo-map" in p.read_text(encoding="utf-8")]
    assert not offenders, f"stale 'workspace-repo-map' brand string in: {offenders}"


def test_no_stale_brand_in_shipped_config():
    text = (ROOT / "example.index.toml").read_text(encoding="utf-8")
    stale = [tok for tok in ("workspace-repo-map", ".repomap.toml") if tok in text]
    assert not stale, f"stale token(s) in example.index.toml: {stale}"
