from pathlib import Path
import shutil
import subprocess

import pytest

from index_graph.freshness.fingerprint import repo_fingerprint
from index_graph.graph.build import build_graph

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="Git required")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True)


def create_repo(path):
    path.mkdir()
    git(path, "init")
    (path / "pyproject.toml").write_text("[project]\nname='example'\n", encoding="utf-8")
    (path / "main.py").write_text("import alpha\n", encoding="utf-8")
    git(path, "add", "pyproject.toml", "main.py")
    return path


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_git_index_flags_cannot_hide_resolver_visible_changes(tmp_path, monkeypatch, flag):
    repo = create_repo(tmp_path / "repo")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    before = repo_fingerprint(repo)
    build_graph({"example": repo}, jobs=1)
    git(repo, "update-index", flag, "main.py")
    (repo / "main.py").write_text("import bravo\n", encoding="utf-8")
    assert repo_fingerprint(repo) != before
    cached = build_graph({"example": repo}, jobs=1)
    fresh = build_graph({"example": repo}, jobs=1, use_cache=False)
    assert cached == fresh
    assert {edge.target_name for edge in cached.edges} == {"bravo"}


def test_identical_working_bytes_have_same_fingerprint_without_git(tmp_path):
    repo = create_repo(tmp_path / "repo")
    plain = tmp_path / "plain"
    plain.mkdir()
    for name in ("main.py", "pyproject.toml"):
        (plain / name).write_bytes((repo / name).read_bytes())
    assert repo_fingerprint(repo) == repo_fingerprint(plain)


def test_gitignore_does_not_silently_reduce_source_coverage(tmp_path):
    repo = create_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text("local.py\n", encoding="utf-8")
    (repo / "local.py").write_text("import local_dependency\n", encoding="utf-8")
    before = repo_fingerprint(repo)
    graph = build_graph({"example": repo}, jobs=1, use_cache=False)
    assert "local-dependency" in {edge.target_name for edge in graph.edges}
    (repo / "local.py").write_text("import changed_dependency\n", encoding="utf-8")
    assert repo_fingerprint(repo) != before
