from __future__ import annotations

from pathlib import Path

from workspace_repo_map.graph.build import build_graph, detect_markers

FIX = Path(__file__).parent / "fixtures"


def test_detect_markers_entry_and_published():
    mk = detect_markers(FIX / "py_app", {"py-app"})
    assert "published" in mk and "entry" in mk


def test_build_graph_links_app_to_lib():
    graph = build_graph({"py-app": FIX / "py_app", "py-lib": FIX / "py_lib"})
    internal = [e for e in graph.edges if not e.external]
    pairs = {(e.from_repo, e.to_repo) for e in internal}
    assert ("py-app", "py-lib") in pairs
    assert "entrypoint" in graph.roles["py-app"]
    assert "hub" in graph.roles["py-lib"] or "library" in graph.roles["py-lib"]
    node = next(n for n in graph.repos if n.name == "py-app")
    assert node.ecosystems == ("python",)
