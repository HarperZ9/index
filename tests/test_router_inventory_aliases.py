from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from index_graph.graph.build import build_graph
from index_graph.graph.walk import GraphSourceError
from index_graph.knowledge.docs import discover_router_docs
from index_graph.router_inventory import build_router_inventory
from index_graph.scan import ScanBudgetExceeded


def _repo(path: Path, project: str, imported: str) -> Path:
    (path / ".git").mkdir(parents=True)
    (path / "pyproject.toml").write_text(
        f"[project]\nname='{project}'\nversion='0.1.0'\n", encoding="utf-8"
    )
    (path / "main.py").write_text(f"import {imported}\n", encoding="utf-8")
    (path / "README.md").write_text(f"# {project}\n", encoding="utf-8")
    return path


def _link(target: Path, alias: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(alias))
    else:
        alias.symlink_to(target, target_is_directory=True)


def _unlink(alias: Path) -> None:
    # Remove only the temporary directory entry, never its target contents.
    if os.name == "nt":
        os.rmdir(alias)
    else:
        alias.unlink()


@pytest.fixture
def aliased_workspace(tmp_path, monkeypatch):
    import index_graph.router_inventory as inventory_mod

    workspace = tmp_path / "workspace"
    local = _repo(workspace / "local" / "package", "local-package", "local_dependency")
    physical = _repo(tmp_path / "offloaded" / "package", "remote-package", "remote_dependency")
    (physical / "docs").mkdir()
    (physical / "docs" / "guide.md").write_text("# Operator guide\n", encoding="utf-8")
    excluded = physical / "node_modules" / "dependency"
    excluded.mkdir(parents=True)
    (excluded / "README.md").write_text("# Excluded\n", encoding="utf-8")
    (excluded / "hidden.py").write_text("import forbidden_dependency\n", encoding="utf-8")
    nested = physical / "vendor" / "nested"
    (nested / ".git").mkdir(parents=True)
    (nested / "main.py").write_text("import nested_dependency\n", encoding="utf-8")
    alias = workspace / "offloaded" / "package"
    alias.parent.mkdir()
    _link(physical, alias)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))

    if os.name != "nt":
        # POSIX walk skips directory symlinks. Emulate Windows junction walking
        # at the walker boundary, preserving the caller's pruning mutations.
        real_walk = os.walk

        def junction_walk(root, **kwargs):
            assert kwargs.get("followlinks", False) is False
            for current, directories, files in real_walk(root, **kwargs):
                yield current, directories, files
                if Path(current) == alias.parent and alias.name in directories:
                    for target_dir, target_dirs, target_files in real_walk(alias.resolve(), **kwargs):
                        lexical = alias / Path(target_dir).relative_to(alias.resolve())
                        yield str(lexical), target_dirs, target_files

        monkeypatch.setattr(inventory_mod, "os", SimpleNamespace(walk=junction_walk))

    try:
        yield workspace, alias, physical, local
    finally:
        if alias.exists():
            _unlink(alias)


def _graph(inventory):
    return build_graph(
        inventory.repo_paths,
        jobs=1,
        executor="thread",
        file_lists=inventory.repo_file_lists,
    )


def test_alias_keeps_duplicate_repo_keys_and_portable_docs(aliased_workspace):
    workspace, alias, physical, local = aliased_workspace

    inventory = build_router_inventory(workspace, budget_ms=0)

    assert inventory.repo_paths == {"local/package": local, "offloaded/package": alias}
    assert inventory.repo_dirs == {
        "local/package": "local/package",
        "offloaded/package": "offloaded/package",
    }
    docs = discover_router_docs(workspace, paths=inventory.router_doc_paths)
    assert [doc.rel_path for doc in docs] == [
        "local/package/README.md",
        "offloaded/package/README.md",
        "offloaded/package/docs/guide.md",
    ]
    assert all(not Path(doc.rel_path).is_absolute() for doc in docs)
    assert physical not in inventory.repo_paths.values()
    assert inventory.stats["repo_count"] == 2


def test_alias_graph_preload_preserves_import_evidence_and_pruning(aliased_workspace, monkeypatch):
    workspace, alias, physical, local = aliased_workspace
    real_scandir = os.scandir
    visited = []

    def checked_scandir(path):
        if not isinstance(path, int):
            candidate = Path(path)
            visited.append(candidate)
            assert "node_modules" not in candidate.parts
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", checked_scandir)
    inventory = build_router_inventory(workspace, budget_ms=0)
    graph = _graph(inventory)

    assert set(inventory.repo_file_lists) == {"local/package", "offloaded/package"}
    assert inventory.stats["repo_inventory_fallbacks"] == 0
    alias_listing = inventory.repo_file_lists["offloaded/package"]
    assert {path.relative_to(physical).as_posix() for path in alias_listing.files} == {
        "README.md", "pyproject.toml", "main.py", "docs/guide.md"
    }
    assert {(edge.from_repo, edge.target_name) for edge in graph.edges} == {
        ("local/package", "local-dependency"),
        ("offloaded/package", "remote-dependency"),
    }
    assert all(signal.evidence_file == "main.py" for edge in graph.edges for signal in edge.signals)
    assert all(signal.evidence_line == 1 for edge in graph.edges for signal in edge.signals)
    assert physical in visited
    assert all("node_modules" not in path.parts for path in inventory.router_doc_paths)


def test_alias_retarget_rejects_stale_inventory_after_warm_cache(aliased_workspace, tmp_path):
    workspace, alias, physical, local = aliased_workspace
    first = _graph(build_router_inventory(workspace, budget_ms=0))
    assert {(edge.from_repo, edge.target_name) for edge in first.edges} == {
        ("local/package", "local-dependency"),
        ("offloaded/package", "remote-dependency"),
    }
    warm = _graph(build_router_inventory(workspace, budget_ms=0))
    assert warm.cache_summary is not None
    assert warm.cache_summary["hits"] == 2
    inventory = build_router_inventory(workspace, budget_ms=0)
    replacement = _repo(tmp_path / "replacement" / "package", "replacement-package", "current_dependency")
    _unlink(alias)
    _link(replacement, alias)

    with pytest.raises(GraphSourceError):
        _graph(inventory)

    graph = _graph(build_router_inventory(workspace, budget_ms=0))

    assert {(edge.from_repo, edge.target_name) for edge in graph.edges} == {
        ("local/package", "local-dependency"),
        ("offloaded/package", "current-dependency"),
    }
    assert (physical / "main.py").read_text(encoding="utf-8") == "import remote_dependency\n"
    assert alias.resolve() == replacement.resolve()


def test_alias_retarget_to_captured_subdirectory_rejects_stale_inventory(aliased_workspace):
    workspace, alias, physical, local = aliased_workspace
    inventory = build_router_inventory(workspace, budget_ms=0)
    assert physical / "docs" in {
        snapshot.path
        for snapshot in inventory.repo_file_lists["offloaded/package"].directory_snapshots
    }
    _graph(inventory)
    _unlink(alias)
    _link(physical / "docs", alias)

    with pytest.raises(GraphSourceError):
        _graph(inventory)

    assert alias.resolve() == physical / "docs"


def test_unreadable_alias_counts_one_fallback(aliased_workspace, monkeypatch):
    import index_graph.router_inventory as inventory_mod

    workspace, alias, physical, local = aliased_workspace
    real_walk = inventory_mod.os.walk

    def unreadable_walk(root, **kwargs):
        for current, directories, files in real_walk(root, **kwargs):
            yield current, directories, files
            if Path(current) == alias:
                kwargs["onerror"](PermissionError(13, "Access denied", str(alias / "docs")))

    monkeypatch.setattr(inventory_mod, "os", SimpleNamespace(walk=unreadable_walk))

    inventory = build_router_inventory(workspace, budget_ms=0)

    assert inventory.stats["repo_inventory_fallbacks"] == 1
    assert set(inventory.repo_file_lists) == {"local/package"}
    assert inventory.skipped == (str(alias / "docs"),)


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows junction traversal semantics")
@pytest.mark.parametrize("repo_kind", ["ordinary", "root_alias"])
@pytest.mark.parametrize("late_source", [False, True], ids=["fresh", "invalidated"])
def test_internal_junction_does_not_add_external_graph_sources(
    aliased_workspace, tmp_path, repo_kind, late_source
):
    workspace, alias, physical, local = aliased_workspace
    external = tmp_path / "outside-repository"
    external.mkdir()
    (external / "sensitive.py").write_text("import external_only_dependency\n", encoding="utf-8")
    (external / "guide.md").write_text("# External guide\n", encoding="utf-8")
    repository = local if repo_kind == "ordinary" else physical
    internal_alias = repository / "linked-docs"
    _link(external, internal_alias)

    try:
        inventory = build_router_inventory(workspace, budget_ms=0)
        expected = {
            ("local/package", "local-dependency"),
            ("offloaded/package", "remote-dependency"),
        }
        if late_source:
            (repository / "late.py").write_text("import newly_added_dependency\n", encoding="utf-8")
            expected.add((
                "local/package" if repo_kind == "ordinary" else "offloaded/package",
                "newly-added-dependency",
            ))
        graph = _graph(inventory)

        assert {(edge.from_repo, edge.target_name) for edge in graph.edges} == expected
        assert all(
            signal.evidence_file == ("late.py" if edge.target_name == "newly-added-dependency" else "main.py")
            for edge in graph.edges
            for signal in edge.signals
        )
        assert (external / "sensitive.py").read_text(encoding="utf-8") == "import external_only_dependency\n"
    finally:
        _unlink(internal_alias)


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows junction traversal semantics")
@pytest.mark.parametrize("repo_kind", ["ordinary", "root_alias"])
@pytest.mark.parametrize("late_source", [False, True], ids=["fresh", "invalidated"])
def test_junction_into_nested_repo_subdirectory_preserves_repo_boundary(
    aliased_workspace, repo_kind, late_source
):
    workspace, alias, physical, local = aliased_workspace
    repository = local if repo_kind == "ordinary" else physical
    nested = repository / "vendor" / "nested"
    (nested / ".git").mkdir(parents=True, exist_ok=True)
    nested_source = nested / "src"
    nested_source.mkdir()
    (nested_source / "only.py").write_text("import nested_only_dependency\n", encoding="utf-8")
    linked = repository / "linked"
    _link(nested_source, linked)

    try:
        inventory = build_router_inventory(workspace, budget_ms=0)
        expected = {
            ("local/package", "local-dependency"),
            ("offloaded/package", "remote-dependency"),
        }
        if late_source:
            (repository / "late.py").write_text("import newly_added_dependency\n", encoding="utf-8")
            expected.add((
                "local/package" if repo_kind == "ordinary" else "offloaded/package",
                "newly-added-dependency",
            ))

        graph = _graph(inventory)

        assert {(edge.from_repo, edge.target_name) for edge in graph.edges} == expected
        assert all(
            signal.evidence_file == ("late.py" if edge.target_name == "newly-added-dependency" else "main.py")
            for edge in graph.edges
            for signal in edge.signals
        )
        assert (nested_source / "only.py").read_text(encoding="utf-8") == "import nested_only_dependency\n"
    finally:
        _unlink(linked)


def test_exhaustion_after_alias_marker_raises_without_partial_inventory(aliased_workspace, monkeypatch):
    import index_graph.router_inventory as inventory_mod

    workspace, alias, physical, local = aliased_workspace
    checkpoints = []

    def exhaust_at_docs(budget, path):
        checkpoints.append(path)
        budget.last_path = path
        if path.name == "docs":
            budget.exhausted = True
            return False
        return True

    constructed = []
    real_inventory = inventory_mod.RouterInventory

    def record_inventory(*args, **kwargs):
        constructed.append(kwargs)
        return real_inventory(*args, **kwargs)

    monkeypatch.setattr(inventory_mod.ScanBudget, "checkpoint", exhaust_at_docs)
    monkeypatch.setattr(inventory_mod, "RouterInventory", record_inventory)

    with pytest.raises(ScanBudgetExceeded) as caught:
        build_router_inventory(workspace, budget_ms=1000)

    assert caught.value.repo_count == 2
    assert caught.value.budget_ms == 1000
    assert caught.value.last_path == str(alias / "docs")
    assert caught.value.skipped == [f"scan-budget-exhausted:{alias / 'docs'}"]
    assert alias in checkpoints
    assert constructed == []
