from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from index_graph.context.pack import to_json
import index_graph.graph.build as build
import index_graph.graph.cache as cache_mod
from index_graph.graph.build import build_graph
from index_graph.graph.resolvers.base import RawEdge
from index_graph.graph.walk import read_source_text


class CountingResolver:
    name = "counting"
    uses_shared_source_reader = True
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
        return {read_source_text(repo_root / "manifest.txt", encoding="utf-8").strip()}

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        self._call()
        deps = repo_root / "deps.txt"
        if not deps.exists():
            return []
        edges: list[RawEdge] = []
        for line_no, target in enumerate(read_source_text(deps, encoding="utf-8").splitlines(), start=1):
            if target:
                edges.append(RawEdge(target, "manifest", "deps.txt", line_no, target))
        return edges


class DirectReadResolver:
    name = "direct-read"
    fingerprint_names = ("manifest.txt", "deps.txt", "README.md")

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def _call(self) -> None:
        if self.fail:
            raise AssertionError("direct resolver should run because cache is unsupported")

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


def test_resolver_implementation_change_invalidates_cached_edges(tmp_path, monkeypatch):
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    repo = _repo(tmp_path / "app", "app", "alpha")
    paths = {"app": repo}
    before = to_json(build_graph(paths, resolvers=(CountingResolver(),), jobs=1))

    def changed_raw_edges(self, root):
        return [RawEdge("beta", "manifest", "deps.txt", 1, "beta")]

    monkeypatch.setattr(CountingResolver, "raw_edges", changed_raw_edges)
    cached = to_json(build_graph(paths, resolvers=(CountingResolver(),), jobs=1))
    actual = to_json(build_graph(paths, resolvers=(CountingResolver(),), jobs=1,
                                use_cache=False))
    assert cached == actual
    assert cached != before


def test_index_release_version_invalidates_graph_cache_key(tmp_path, monkeypatch):
    import index_graph.graph.cache as cache_mod

    repo = _repo(tmp_path / "app", "app", "alpha")
    before = cache_mod.make_lookup("app", repo, (CountingResolver(),)).key
    monkeypatch.setattr(cache_mod, "__version__", "999.0.0", raising=False)
    assert cache_mod.make_lookup("app", repo, (CountingResolver(),)).key != before


def test_fresh_interpreter_resolver_warmup_keeps_one_cache_entry(tmp_path):
    # Isolate from suite order: earlier tests may already have warmed resolvers.
    script = """
import json, sys
from pathlib import Path
from index_graph.graph.build import build_graph
root = Path(sys.argv[1])
repo = root / 'repo'
repo.mkdir(exist_ok=True)
(repo / 'pyproject.toml').write_text('[project]\\nname="sample"\\n')
(repo / 'main.py').write_text('import alpha\\n')
for _ in range(3):
    graph = build_graph({'sample': repo}, jobs=1)
    assert {edge.target_name for edge in graph.edges} == {'alpha'}
print(json.dumps({'cache_files': len(list((root / 'cache').glob('*.json')))}))
"""
    env = dict(os.environ, INDEX_GRAPH_REPO_CACHE_DIR=str(tmp_path / "cache"),
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["cache_files"] == 1


def test_unopted_custom_resolver_bypasses_cache_reads_and_writes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    paths = {"app": _repo(tmp_path / "app", "app", "lib")}

    first = to_json(build_graph(paths, resolvers=(DirectReadResolver(),), jobs=1))

    assert {rel["target_name"] for rel in first["relations"]} == {"lib"}
    assert list((tmp_path / "cache").glob("*.json")) == []
    with pytest.raises(AssertionError, match="direct resolver should run"):
        build_graph(paths, resolvers=(DirectReadResolver(fail=True),), jobs=1)


def test_unopted_custom_resolver_ignores_existing_stale_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    repo = _repo(tmp_path / "app", "app", "lib")
    resolver = DirectReadResolver()
    lookup = cache_mod.make_lookup("app", repo, (resolver,))
    cache_mod.write_repo_build(lookup, {
        "node": {
            "name": "app",
            "path": str(repo.resolve()),
            "ecosystems": ["direct-read"],
            "exposed_names": ["app"],
            "description": "poisoned cache entry",
            "markers": [],
        },
        "exposed_names": ["app"],
        "raw_edges": [{
            "target_name": "poison",
            "signal": "manifest",
            "evidence_file": "deps.txt",
            "evidence_line": 1,
            "raw_spec": "poison",
        }],
        "markers": [],
    })

    graph = to_json(build_graph({"app": repo}, resolvers=(DirectReadResolver(),), jobs=1))

    assert {rel["target_name"] for rel in graph["relations"]} == {"lib"}


@pytest.mark.parametrize("cache_bytes", [0, 1024 * 1024])
def test_unopted_direct_reader_race_does_not_persist_cache(
    tmp_path: Path, monkeypatch, cache_bytes: int
):
    import index_graph.graph.walk as walk

    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_BYTES", cache_bytes)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    repo = _repo(tmp_path / "app", "app", "alpha")
    original = build.make_lookup
    race_triggered = False

    def changed_after_fingerprint(*args, **kwargs):
        nonlocal race_triggered
        lookup = original(*args, **kwargs)
        (repo / "deps.txt").write_text("bravo", encoding="utf-8")
        race_triggered = True
        return lookup

    monkeypatch.setattr(build, "make_lookup", changed_after_fingerprint)

    graph = to_json(build_graph({"app": repo}, resolvers=(DirectReadResolver(),), jobs=1))

    assert race_triggered is False
    assert {rel["target_name"] for rel in graph["relations"]} == {"alpha"}
    assert list((tmp_path / "cache").glob("*.json")) == []


def test_mixed_resolver_set_with_unopted_custom_resolver_bypasses_cache(
    tmp_path: Path, monkeypatch
):
    from index_graph.graph.resolvers.python import PythonResolver

    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    repo = _repo(tmp_path / "app", "app", "custom-lib")
    (repo / "pyproject.toml").write_text("[project]\nname='app'\n", encoding="utf-8")
    (repo / "main.py").write_text("import python_lib\n", encoding="utf-8")
    paths = {"app": repo}

    graph = to_json(build_graph(paths, resolvers=(PythonResolver(), DirectReadResolver()), jobs=1))

    assert {rel["target_name"] for rel in graph["relations"]} == {"custom-lib", "python-lib"}
    assert list((tmp_path / "cache").glob("*.json")) == []
    with pytest.raises(AssertionError, match="direct resolver should run"):
        build_graph(paths, resolvers=(PythonResolver(), DirectReadResolver(fail=True)), jobs=1)


@pytest.mark.parametrize("cache_bytes", [0, 1024 * 1024])
def test_shared_reader_custom_resolver_can_use_cache(
    tmp_path: Path, monkeypatch, cache_bytes: int
):
    import index_graph.graph.walk as walk

    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_BYTES", cache_bytes)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    paths = {"app": _repo(tmp_path / "app", "app", "lib")}

    first = to_json(build_graph(paths, resolvers=(CountingResolver(),), jobs=1))
    second = to_json(build_graph(paths, resolvers=(CountingResolver(fail=True),), jobs=1))

    assert {rel["target_name"] for rel in first["relations"]} == {"lib"}
    assert second == first
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_shared_reader_contract_changes_repo_cache_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    repo = _repo(tmp_path / "app", "app", "lib")
    root = repo.resolve()
    resolver = CountingResolver()
    fingerprint = cache_mod.repo_graph_fingerprint(root, (resolver,))
    signature = cache_mod._resolver_signature((resolver,))
    old_payload = {
        "version": "repo-build/v3",
        "index_version": cache_mod.__version__,
        "repo_name": "app",
        "repo_path": str(root),
        "fingerprint": fingerprint,
        "resolver_signature": signature,
    }
    old_key = cache_mod._sha256_text(json.dumps(old_payload, sort_keys=True, separators=(",", ":")))

    current = cache_mod.make_lookup("app", repo, (resolver,))

    assert current.key != old_key
