"""The retired workspace-repo-map package: importing it warns and names index-graph."""
import importlib.util
import tomllib
import warnings
from pathlib import Path

SHIM = Path(__file__).resolve().parents[1] / "compat" / "workspace-repo-map"


def _load():
    spec = importlib.util.spec_from_file_location(
        "workspace_repo_map_shim", SHIM / "src" / "workspace_repo_map" / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spec.loader.exec_module(module)
    return module, caught


def test_import_warns_once_and_names_the_new_package():
    module, caught = _load()
    assert [w.category for w in caught] == [DeprecationWarning]
    message = str(caught[0].message)
    assert "index-graph" in message and "pip install index-graph" in message
    assert module.__version__ == "0.2.1"


def test_metadata_matches_the_module_and_adds_no_command_or_dependency():
    project = tomllib.loads((SHIM / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    module, _ = _load()
    assert project["name"] == "workspace-repo-map"
    assert project["version"] == module.__version__
    assert project["dependencies"] == []
    assert "scripts" not in project


def test_the_index_graph_sdist_leaves_the_shim_out():
    root = tomllib.loads((SHIM.parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    assert "/compat" in root["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
