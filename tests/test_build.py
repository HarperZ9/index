from __future__ import annotations

from pathlib import Path

from index_graph.context.pack import to_json
from index_graph.graph.build import build_graph, detect_markers
import index_graph.graph.walk as walk_mod

FIX = Path(__file__).parent / "fixtures"


def test_detect_markers_entry_and_published():
    mk = detect_markers(FIX / "py-app", {"py-app"})
    assert "published" in mk and "entry" in mk


def test_build_graph_links_app_to_lib():
    graph = build_graph({"py-app": FIX / "py-app", "py-lib": FIX / "py-lib"})
    internal = [e for e in graph.edges if not e.external]
    pairs = {(e.from_repo, e.to_repo) for e in internal}
    assert ("py-app", "py-lib") in pairs
    assert "entrypoint" in graph.roles["py-app"]
    assert "hub" in graph.roles["py-lib"] or "library" in graph.roles["py-lib"]
    node = next(n for n in graph.repos if n.name == "py-app")
    assert node.ecosystems == ("python",)
    # M1 regression: a library that exposes both its dist name and package-dir name
    # (both normalize to the same key) must NOT trigger the ambiguity path.
    edge = next(e for e in internal if (e.from_repo, e.to_repo) == ("py-app", "py-lib"))
    assert edge.confidence == "high"      # both manifest + import signals
    assert graph.warnings == ()           # no spurious ambiguity warnings


def test_build_graph_parallel_output_matches_serial_output():
    paths = {"py-app": FIX / "py-app", "py-lib": FIX / "py-lib"}

    serial = to_json(build_graph(paths, jobs=1))
    parallel = to_json(build_graph(paths, jobs=4))

    assert parallel == serial


def test_build_graph_does_not_attribute_nested_repo_files_to_parent(tmp_path: Path):
    root = tmp_path / "workspace-root"
    child = root / "child"
    (root / ".git").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\nname = \"rootproj\"\n",
        encoding="utf-8",
    )
    (child / ".git").mkdir(parents=True)
    (child / "pyproject.toml").write_text(
        "[project]\nname = \"childproj\"\n",
        encoding="utf-8",
    )
    (child / "module.py").write_text("import requests\n", encoding="utf-8")

    graph = build_graph({"root": root, "child": child}, use_cache=False, jobs=1)

    parent_external = {
        edge.target_name for edge in graph.edges
        if edge.from_repo == "root" and edge.external
    }
    child_external = {
        edge.target_name for edge in graph.edges
        if edge.from_repo == "child" and edge.external
    }
    assert "requests" not in parent_external
    assert "requests" in child_external


def test_build_graph_reuses_file_listing_within_repo_build(tmp_path: Path, monkeypatch):
    repo = tmp_path / "app"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "app"\ndependencies = ["requests"]\n', encoding="utf-8")
    (repo / "main.py").write_text("import requests\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    real_walk = walk_mod.os.walk
    calls = []

    def counted_walk(root, *args, **kwargs):
        calls.append(root)
        yield from real_walk(root, *args, **kwargs)

    monkeypatch.setattr(walk_mod.os, "walk", counted_walk)
    graph = build_graph({"app": repo}, use_cache=True, jobs=1)
    assert len(graph.repos) == 1
    assert calls == [repo]
