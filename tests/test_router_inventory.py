from __future__ import annotations

import os
from pathlib import Path

import pytest

from index_graph.cli_handlers._common import rel_to_root, repo_paths
from index_graph.graph.build import build_graph
from index_graph.knowledge.atlas import build_router_pack
from index_graph.knowledge.docs import discover_router_docs
from index_graph.router import render_router
from index_graph.router_inventory import build_router_inventory


def _repo(path: Path, project_name: str, source: str = "") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / "pyproject.toml").write_text(
        f"[project]\nname='{project_name}'\nversion='0'\n", encoding="utf-8"
    )
    if source:
        (path / "main.py").write_text(source, encoding="utf-8")
    return path


def _router_text_legacy(root: Path) -> str:
    paths = repo_paths(root, budget_ms=0)
    repo_dirs = {name: rel_to_root(root, path) for name, path in paths.items()}
    graph = build_graph(paths, jobs=1, executor="thread")
    docs = discover_router_docs(root)
    return render_router(build_router_pack(graph, docs, repo_dirs), max_docs=100)


def _router_text_with_inventory(root: Path) -> tuple[str, dict[str, int]]:
    inventory = build_router_inventory(root, budget_ms=0)
    graph = build_graph(
        inventory.repo_paths,
        jobs=1,
        executor="thread",
        file_lists=inventory.repo_file_lists,
    )
    docs = discover_router_docs(root, paths=inventory.router_doc_paths)
    text = render_router(build_router_pack(graph, docs, inventory.repo_dirs), max_docs=100)
    return text, inventory.stats


def _graph_with_inventory(inventory):
    return build_graph(
        inventory.repo_paths,
        jobs=1,
        executor="thread",
        file_lists=inventory.repo_file_lists,
    )


def _build_fixture(root: Path) -> Path:
    workspace = root / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Workspace\n", encoding="utf-8")

    app = _repo(workspace / "packages" / "app", "app", "import alpha\n")
    (app / "docs").mkdir()
    (app / "docs" / "guide.md").write_text("# App Guide\n", encoding="utf-8")
    nested = app / "vendor" / "nested"
    (nested / ".git").mkdir(parents=True)
    (nested / "nested.py").write_text("import nested_dep\n", encoding="utf-8")
    (nested / "README.md").write_text("# Nested Doc\n", encoding="utf-8")
    (app / "node_modules" / "pkg").mkdir(parents=True)
    (app / "node_modules" / "pkg" / "README.md").write_text("# Ignored\n", encoding="utf-8")
    (app / "node_modules" / "pkg" / "ignored.py").write_text(
        "import ignored_dep\n", encoding="utf-8"
    )

    _repo(workspace / "packages" / "application", "application")
    (workspace / "packages" / "application" / "README.md").write_text(
        "# Application\n", encoding="utf-8"
    )

    worktree = workspace / "worktrees" / "bravo"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../.git/worktrees/bravo\n", encoding="utf-8")
    (worktree / "pyproject.toml").write_text(
        "[project]\nname='bravo'\nversion='0'\n", encoding="utf-8"
    )
    (worktree / "README.md").write_text("# Bravo\n", encoding="utf-8")
    return workspace


def test_router_inventory_reuses_walks_without_changing_router_output(tmp_path, monkeypatch):
    # Catches an inventory path that changes router evidence, crosses nested
    # repo boundaries, includes excluded directories, or still performs the
    # legacy repo + graph + docs traversal fan-out.
    import index_graph.graph.walk as walk_mod
    import index_graph.router_inventory as inventory_mod
    import index_graph.scan as scan_mod

    workspace = _build_fixture(tmp_path)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))

    walk_counts = {"legacy": 0, "inventory": 0}
    scandir_counts = {"legacy": 0, "inventory": 0}
    phase = {"name": "legacy"}
    real_scan_walk = scan_mod.os.walk
    real_graph_walk = walk_mod.os.walk
    real_inventory_walk = inventory_mod.os.walk
    real_scandir = os.scandir

    def count_legacy_scan(*args, **kwargs):
        walk_counts["legacy"] += 1
        yield from real_scan_walk(*args, **kwargs)

    def count_legacy_graph(*args, **kwargs):
        walk_counts["legacy"] += 1
        yield from real_graph_walk(*args, **kwargs)

    def count_scandir(*args, **kwargs):
        scandir_counts[phase["name"]] += 1
        return real_scandir(*args, **kwargs)

    monkeypatch.setattr(os, "scandir", count_scandir)
    monkeypatch.setattr(scan_mod.os, "walk", count_legacy_scan)
    monkeypatch.setattr(walk_mod.os, "walk", count_legacy_graph)
    legacy = _router_text_legacy(workspace)
    legacy_walks = walk_counts["legacy"]
    legacy_scandir = scandir_counts["legacy"]
    phase["name"] = "inventory"

    def count_inventory(*args, **kwargs):
        walk_counts["inventory"] += 1
        yield from real_inventory_walk(*args, **kwargs)

    monkeypatch.setattr(inventory_mod.os, "walk", count_inventory)
    inventory_text, stats = _router_text_with_inventory(workspace)

    assert inventory_text == legacy
    assert walk_counts["inventory"] == 1
    assert stats["physical_walks"] == 1
    assert stats["repo_count"] == 3
    assert stats["router_doc_paths"] == 5
    assert legacy_walks > walk_counts["inventory"]
    assert legacy_scandir > scandir_counts["inventory"]
    assert "`packages/app/docs/guide.md` describes `app`" in inventory_text
    assert "`packages/application/README.md` describes `application`" in inventory_text
    assert "node_modules" not in inventory_text
    assert "ignored-dep" not in inventory_text
    assert "nested-dep" not in inventory_text


def test_router_inventory_preserves_exact_byte_cache_invalidation_after_restored_mtime(
    tmp_path, monkeypatch
):
    # Catches a traversal optimization that downgrades cache admission to
    # size/mtime metadata and misses equal-size source-byte changes.
    workspace = _build_fixture(tmp_path)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    source = workspace / "packages" / "app" / "main.py"
    before_stat = source.stat()

    first_inventory = build_router_inventory(workspace, budget_ms=0)
    first = build_graph(
        first_inventory.repo_paths,
        jobs=1,
        executor="thread",
        file_lists=first_inventory.repo_file_lists,
    )
    assert {edge.target_name for edge in first.edges} == {"alpha"}

    second_inventory = build_router_inventory(workspace, budget_ms=0)
    warm = build_graph(
        second_inventory.repo_paths,
        jobs=1,
        executor="thread",
        file_lists=second_inventory.repo_file_lists,
    )
    assert warm.cache_summary is not None
    assert warm.cache_summary["hits"] == 3

    source.write_text("import bravo\n", encoding="utf-8")
    os.utime(source, ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns))

    changed_inventory = build_router_inventory(workspace, budget_ms=0)
    changed = build_graph(
        changed_inventory.repo_paths,
        jobs=1,
        executor="thread",
        file_lists=changed_inventory.repo_file_lists,
    )

    assert {edge.target_name for edge in changed.edges} == {"bravo"}
    assert changed.cache_summary is not None
    assert changed.cache_summary["hits"] == 2
    assert changed.cache_summary["misses"] == 1


def test_router_inventory_revalidates_graph_scope_before_warm_cache_hit(
    tmp_path, monkeypatch
):
    # Catches a preloaded file list that hides a graph-relevant source added
    # after inventory enumeration and returns a stale warm cache hit.
    workspace = _build_fixture(tmp_path)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))

    warm_inventory = build_router_inventory(workspace, budget_ms=0)
    assert {edge.target_name for edge in _graph_with_inventory(warm_inventory).edges} == {"alpha"}

    stale_inventory = build_router_inventory(workspace, budget_ms=0)
    (workspace / "packages" / "app" / "late.py").write_text(
        "import beta\n", encoding="utf-8"
    )

    changed = _graph_with_inventory(stale_inventory)

    assert {edge.target_name for edge in changed.edges} == {"alpha", "beta"}
    assert changed.cache_summary is not None
    assert changed.cache_summary["hits"] == 2
    assert changed.cache_summary["misses"] == 1


def test_router_inventory_revalidates_late_added_subdir_before_graph_scope(
    tmp_path, monkeypatch
):
    # Catches a preloaded file list that misses a graph-relevant source added
    # inside a new directory after inventory enumeration.
    workspace = _build_fixture(tmp_path)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))

    warm_inventory = build_router_inventory(workspace, budget_ms=0)
    assert {edge.target_name for edge in _graph_with_inventory(warm_inventory).edges} == {"alpha"}

    stale_inventory = build_router_inventory(workspace, budget_ms=0)
    generated = workspace / "packages" / "app" / "generated"
    generated.mkdir()
    (generated / "late.py").write_text("import eta\n", encoding="utf-8")

    changed = _graph_with_inventory(stale_inventory)

    assert {edge.target_name for edge in changed.edges} == {"alpha", "eta"}
    assert changed.cache_summary is not None
    assert changed.cache_summary["hits"] == 2
    assert changed.cache_summary["misses"] == 1


def test_router_inventory_revalidates_deleted_subdir_before_graph_scope(
    tmp_path, monkeypatch
):
    # Catches a preloaded file list that treats a deleted directory as either a
    # readable old source or a graph-source failure instead of rewalking.
    workspace = _build_fixture(tmp_path)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    app = workspace / "packages" / "app"
    removable = app / "removable"
    removable.mkdir()
    (removable / "gone.py").write_text("import gamma\n", encoding="utf-8")

    warm_inventory = build_router_inventory(workspace, budget_ms=0)
    assert {edge.target_name for edge in _graph_with_inventory(warm_inventory).edges} == {
        "alpha",
        "gamma",
    }

    stale_inventory = build_router_inventory(workspace, budget_ms=0)
    (removable / "gone.py").unlink()
    removable.rmdir()

    changed = _graph_with_inventory(stale_inventory)

    assert {edge.target_name for edge in changed.edges} == {"alpha"}
    assert changed.cache_summary is not None
    assert changed.cache_summary["hits"] == 2
    assert changed.cache_summary["misses"] == 1


def test_router_inventory_revalidates_late_nested_git_dir_before_graph_scope(
    tmp_path, monkeypatch
):
    # Catches a preloaded file list that ignores a late .git directory marker
    # and keeps treating a child repository as part of the parent graph.
    workspace = _build_fixture(tmp_path)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    child = workspace / "packages" / "app" / "nested-child"
    child.mkdir()
    (child / "child.py").write_text("import theta\n", encoding="utf-8")

    warm_inventory = build_router_inventory(workspace, budget_ms=0)
    assert {edge.target_name for edge in _graph_with_inventory(warm_inventory).edges} == {
        "alpha",
        "theta",
    }

    stale_inventory = build_router_inventory(workspace, budget_ms=0)
    (child / ".git").mkdir()

    changed = _graph_with_inventory(stale_inventory)

    assert {edge.target_name for edge in changed.edges} == {"alpha"}
    assert changed.cache_summary is not None
    assert changed.cache_summary["hits"] == 2
    assert changed.cache_summary["misses"] == 1


def test_router_inventory_revalidates_late_worktree_marker_before_graph_scope(
    tmp_path, monkeypatch
):
    # Catches a preloaded file list that ignores a late .git file marker and
    # keeps treating a child worktree as part of the parent repository graph.
    workspace = _build_fixture(tmp_path)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    child = workspace / "packages" / "app" / "generated"
    child.mkdir()
    (child / "child.py").write_text("import delta\n", encoding="utf-8")

    warm_inventory = build_router_inventory(workspace, budget_ms=0)
    assert {edge.target_name for edge in _graph_with_inventory(warm_inventory).edges} == {
        "alpha",
        "delta",
    }

    stale_inventory = build_router_inventory(workspace, budget_ms=0)
    (child / ".git").write_text("gitdir: ../.git/worktrees/generated\n", encoding="utf-8")

    changed = _graph_with_inventory(stale_inventory)

    assert {edge.target_name for edge in changed.edges} == {"alpha"}
    assert changed.cache_summary is not None
    assert changed.cache_summary["hits"] == 2
    assert changed.cache_summary["misses"] == 1


def test_router_inventory_revalidates_changed_entry_type_before_graph_scope(
    tmp_path, monkeypatch
):
    # Catches a preloaded file list that reads an old file path after it became
    # a directory instead of rewalking the current tree.
    workspace = _build_fixture(tmp_path)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    app = workspace / "packages" / "app"
    swapped = app / "swapped.py"
    swapped.write_text("import epsilon\n", encoding="utf-8")

    warm_inventory = build_router_inventory(workspace, budget_ms=0)
    assert {edge.target_name for edge in _graph_with_inventory(warm_inventory).edges} == {
        "alpha",
        "epsilon",
    }

    stale_inventory = build_router_inventory(workspace, budget_ms=0)
    swapped.unlink()
    swapped.mkdir()
    (swapped / "inside.py").write_text("import zeta\n", encoding="utf-8")

    changed = _graph_with_inventory(stale_inventory)

    assert {edge.target_name for edge in changed.edges} == {"alpha", "zeta"}
    assert changed.cache_summary is not None
    assert changed.cache_summary["hits"] == 2
    assert changed.cache_summary["misses"] == 1


def test_router_inventory_checkpoint_rejection_raises_typed_interruption(tmp_path):
    # Catches a rejected traversal checkpoint returning a partial inventory that
    # callers can mistake for a complete discovery.
    import index_graph.router_inventory as inventory_mod

    workspace = tmp_path / "workspace"
    _repo(workspace / "a", "a")
    _repo(workspace / "z", "z")
    interruption = getattr(inventory_mod, "RouterInventoryInterrupted")

    def checkpoint(path: Path) -> bool:
        return path.name != "z"

    with pytest.raises(interruption):
        build_router_inventory(workspace, budget_ms=0, checkpoint=checkpoint)
