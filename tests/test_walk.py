from __future__ import annotations

import shutil
import subprocess

import pytest

from index_graph.graph.walk import EXCLUDE_DIRS, walk_files


def _make(root):
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "buried.py").write_text("y = 2\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "dep.js").write_text("z\n", encoding="utf-8")
    (root / "target" / "debug").mkdir(parents=True)
    (root / "target" / "debug" / "buried.py").write_text("z = 3\n", encoding="utf-8")
    (root / "pkg" / "__main__.py").write_text("main\n", encoding="utf-8")


def test_walk_prunes_excluded_dirs_by_suffix(tmp_path):
    _make(tmp_path)
    found = {p.name for p in walk_files(tmp_path, suffixes=(".py",))}
    assert "a.py" in found
    assert "buried.py" not in found          # under .venv -> pruned
    assert ".venv" in EXCLUDE_DIRS and "node_modules" in EXCLUDE_DIRS
    assert "target" in EXCLUDE_DIRS


def test_walk_matches_by_exact_name(tmp_path):
    _make(tmp_path)
    found = {p.name for p in walk_files(tmp_path, names=("__main__.py",))}
    assert found == {"__main__.py"}


def test_walk_missing_root_is_empty_not_error(tmp_path):
    assert list(walk_files(tmp_path / "does-not-exist", suffixes=(".py",))) == []


def test_walk_can_stop_at_nested_repo_directory_boundary(tmp_path):
    _make(tmp_path)
    child = tmp_path / "pkg" / "child-repo"
    (child / ".git").mkdir(parents=True)
    (child / "nested.py").write_text("import requests\n", encoding="utf-8")

    found = {
        p.relative_to(tmp_path).as_posix()
        for p in walk_files(tmp_path, suffixes=(".py",), stop_at_nested_repos=True)
    }

    assert "pkg/a.py" in found
    assert "pkg/child-repo/nested.py" not in found


def test_walk_can_stop_at_nested_worktree_git_file_boundary(tmp_path):
    _make(tmp_path)
    child = tmp_path / "pkg" / "child-worktree"
    child.mkdir(parents=True)
    (child / ".git").write_text("gitdir: ../.git/worktrees/child\n", encoding="utf-8")
    (child / "nested.py").write_text("import requests\n", encoding="utf-8")

    found = {
        p.relative_to(tmp_path).as_posix()
        for p in walk_files(tmp_path, suffixes=(".py",), stop_at_nested_repos=True)
    }

    assert "pkg/a.py" in found
    assert "pkg/child-worktree/nested.py" not in found


def test_walk_still_enters_plain_nested_source_directories(tmp_path):
    _make(tmp_path)
    nested = tmp_path / "pkg" / "subpkg"
    nested.mkdir()
    (nested / "nested.py").write_text("import requests\n", encoding="utf-8")

    found = {
        p.relative_to(tmp_path).as_posix()
        for p in walk_files(tmp_path, suffixes=(".py",), stop_at_nested_repos=True)
    }

    assert "pkg/a.py" in found
    assert "pkg/subpkg/nested.py" in found


def test_walk_keeps_ignored_working_files_with_nested_repo_boundaries(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is required for git-scoped walk coverage")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "visible.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "buried.py").write_text("z = 1\n", encoding="utf-8")
    child = tmp_path / "child"
    (child / ".git").mkdir(parents=True)
    (child / "nested.py").write_text("import requests\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", ".gitignore", "tracked.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    found = {
        p.relative_to(tmp_path).as_posix()
        for p in walk_files(tmp_path, suffixes=(".py",), stop_at_nested_repos=True)
    }

    assert found == {"tracked.py", "visible.py", "ignored/buried.py"}


def test_scoped_walk_checks_budget_during_traversal_and_does_not_cache_partial(tmp_path, monkeypatch):
    import index_graph.graph.walk as walk_mod

    (tmp_path / "root.py").write_text("import root_dep\n", encoding="utf-8")
    def bounded_walk(root, *args, **kwargs):
        yield str(root), [], ["root.py"]
        raise AssertionError("walk continued after budget rejection")

    with walk_mod.cached_file_scope():
        with monkeypatch.context() as patch:
            patch.setattr(walk_mod.os, "walk", bounded_walk)
            assert list(walk_files(tmp_path, suffixes=(".py",),
                                   stop_at_nested_repos=True,
                                   checkpoint=lambda path: False)) == []
        assert [path.name for path in walk_files(tmp_path, suffixes=(".py",),
                                                stop_at_nested_repos=True)] == ["root.py"]
