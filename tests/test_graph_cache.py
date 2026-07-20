from __future__ import annotations

import json
from pathlib import Path

import pytest

from index_graph.context.pack import to_json
from index_graph.graph.build import build_graph
from index_graph.graph.resolvers.base import RawEdge


class CountingResolver:
    name = "counting"
    fingerprint_names = ("manifest.txt", "deps.txt", "README.md")

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def _call(self) -> None:
        self.calls += 1
        if self.fail:
            raise AssertionError("resolver should not run on a cache hit")

    def matches(self, repo_root: Path) -> bool:
        self._call()
        return (repo_root / "manifest.txt").is_file()

    def exposed_names(self, repo_root: Path) -> set[str]:
        self._call()
        return {(repo_root / "manifest.txt").read_text(encoding="utf-8").strip()}

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        self._call()
        deps = repo_root / "deps.txt"
        if not deps.exists():
            return []
        edges: list[RawEdge] = []
        for line_no, target in enumerate(deps.read_text(encoding="utf-8").splitlines(), start=1):
            if target:
                edges.append(RawEdge(target, "manifest", "deps.txt", line_no, target))
        return edges


def _repo(path: Path, name: str, deps: str = "") -> Path:
    path.mkdir(parents=True)
    (path / ".git").mkdir()
    (path / "manifest.txt").write_text(name, encoding="utf-8")
    (path / "deps.txt").write_text(deps, encoding="utf-8")
    (path / "README.md").write_text(f"{name} description", encoding="utf-8")
    return path


def test_build_graph_reuses_unchanged_repo_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    paths = {"app": _repo(tmp_path / "app", "app", "lib")}

    first_resolver = CountingResolver()
    first = to_json(build_graph(paths, resolvers=(first_resolver,), jobs=1))

    second_resolver = CountingResolver(fail=True)
    second = to_json(build_graph(paths, resolvers=(second_resolver,), jobs=1))

    assert first == second
    assert first_resolver.calls > 0
    assert second_resolver.calls == 0


def test_build_graph_invalidates_repo_cache_on_fingerprint_change(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    repo = _repo(tmp_path / "app", "app", "lib")
    paths = {"app": repo}

    first = to_json(build_graph(paths, resolvers=(CountingResolver(),), jobs=1))
    (repo / "deps.txt").write_text("other", encoding="utf-8")
    second = to_json(build_graph(paths, resolvers=(CountingResolver(),), jobs=1))

    first_targets = {rel["target_name"] for rel in first["relations"]}
    second_targets = {rel["target_name"] for rel in second["relations"]}
    assert "lib" in first_targets
    assert "other" in second_targets
    assert first != second


def test_build_graph_cache_can_be_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    paths = {"app": _repo(tmp_path / "app", "app", "lib")}

    build_graph(paths, resolvers=(CountingResolver(),), jobs=1)

    with pytest.raises(AssertionError, match="resolver should not run"):
        build_graph(paths, resolvers=(CountingResolver(fail=True),), jobs=1, use_cache=False)


def test_build_graph_ignores_corrupt_repo_cache(tmp_path: Path, monkeypatch):
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(cache_dir))
    paths = {"app": _repo(tmp_path / "app", "app", "lib")}

    first = to_json(build_graph(paths, resolvers=(CountingResolver(),), jobs=1))
    for cache_file in cache_dir.glob("*.json"):
        cache_file.write_text("{not json", encoding="utf-8")
    second = to_json(build_graph(paths, resolvers=(CountingResolver(),), jobs=1))

    assert second == first
    assert any(json.loads(path.read_text(encoding="utf-8")) for path in cache_dir.glob("*.json"))
