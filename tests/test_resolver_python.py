from __future__ import annotations

from pathlib import Path

from workspace_repo_map.graph.resolvers.base import normalize_name
from workspace_repo_map.graph.resolvers.python import PythonResolver

FIX = Path(__file__).parent / "fixtures"


def test_normalize_name():
    assert normalize_name("My_Pkg") == "my-pkg"
    assert normalize_name("  rich ") == "rich"


def test_matches_python_repo():
    assert PythonResolver().matches(FIX / "py_lib") is True
    assert PythonResolver().matches(FIX / "py_app") is True


def test_exposed_names_includes_dist_and_packages():
    names = PythonResolver().exposed_names(FIX / "py_lib")
    norm = {normalize_name(n) for n in names}
    assert "py-lib" in norm  # dist name


def test_raw_edges_manifest_and_import():
    edges = PythonResolver().raw_edges(FIX / "py_app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("py-lib", "manifest") in by
    assert ("py_lib", "import") in by
    # evidence is always populated
    assert all(e.evidence_file for e in edges)
    imp = next(e for e in edges if e.signal == "import" and e.target_name == "py_lib")
    assert imp.evidence_line is not None
