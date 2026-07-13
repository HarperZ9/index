import os
import subprocess
from pathlib import Path

import index_graph.gitmeta as gitmeta
from index_graph.gitmeta import repo_metadata, run_git, sanitize_credentials


def test_sanitize_redacts_userinfo_but_keeps_host():
    assert sanitize_credentials("https://tok@github.com/o/r.git") == \
        "https://<redacted>@github.com/o/r.git"


def test_sanitize_redacts_secret_query():
    assert sanitize_credentials("https://example.com/r.git?token=abc") == \
        "https://example.com/r.git?token=<redacted>"


def test_sanitize_leaves_ssh_user_alone():
    assert sanitize_credentials("git@github.com:o/r.git") == "git@github.com:o/r.git"


def test_repo_metadata_degrades_on_non_repo(tmp_path: Path):
    meta = repo_metadata(tmp_path)  # not a git repo -> all git calls return ""
    assert meta["branch"] == "unknown"
    assert meta["head"] == "unknown"
    assert meta["dirty_count"] == 0


def test_repo_metadata_reads_real_repo(tmp_path: Path):
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.t"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"],
                   check=True, capture_output=True)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "i"], check=True,
                   capture_output=True)
    meta = repo_metadata(tmp_path)
    assert meta["branch"] == "main"
    assert meta["head"] != "unknown"


def test_run_git_timeout_returns_empty(monkeypatch, tmp_path):
    import subprocess
    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=20)
    monkeypatch.setattr(subprocess, "run", _raise)
    assert run_git(tmp_path, ["status"]) == ""


def _linked_worktree_fixture(tmp_path: Path) -> tuple[Path, Path]:
    admin = tmp_path / "main" / ".git" / "worktrees" / "feature"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n", encoding="utf-8")
    linked = tmp_path / "worktrees" / "feature"
    linked.mkdir(parents=True)
    (linked / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (admin / "gitdir").write_text(f"{linked / '.git'}\n", encoding="utf-8")
    return linked, admin


def test_gitfile_backlink_matches_registered_linked_worktree(tmp_path: Path):
    linked, _ = _linked_worktree_fixture(tmp_path)
    assert gitmeta.gitfile_backlink_matches(linked)


def test_gitfile_backlink_rejects_copied_linked_worktree(tmp_path: Path):
    linked, _ = _linked_worktree_fixture(tmp_path)
    copied = tmp_path / "audit" / "source"
    copied.mkdir(parents=True)
    (copied / ".git").write_text(
        (linked / ".git").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert not gitmeta.gitfile_backlink_matches(copied)


def test_gitfile_backlink_resolves_relative_paths(tmp_path: Path):
    linked, admin = _linked_worktree_fixture(tmp_path)
    (linked / ".git").write_text(
        f"gitdir: {os.path.relpath(admin, linked)}\n", encoding="utf-8"
    )
    (admin / "gitdir").write_text(
        f"{os.path.relpath(linked / '.git', admin)}\n", encoding="utf-8"
    )
    assert gitmeta.gitfile_backlink_matches(linked)


def test_gitfile_without_worktree_backlink_is_accepted(tmp_path: Path):
    admin = tmp_path / "super" / ".git" / "modules" / "sub"
    admin.mkdir(parents=True)
    submodule = tmp_path / "super" / "sub"
    submodule.mkdir()
    (submodule / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    assert gitmeta.gitfile_backlink_matches(submodule)


def test_empty_gitfile_marker_is_accepted(tmp_path: Path):
    (tmp_path / ".git").write_text("", encoding="utf-8")
    assert gitmeta.gitfile_backlink_matches(tmp_path)


def test_malformed_gitfile_marker_is_accepted(tmp_path: Path):
    (tmp_path / ".git").write_text("not a gitdir record\n", encoding="utf-8")
    assert gitmeta.gitfile_backlink_matches(tmp_path)


def test_separate_git_dir_with_unrelated_gitdir_file_is_accepted(tmp_path: Path):
    repo = tmp_path / "separate"
    repo.mkdir()
    admin = tmp_path / "admin"
    admin.mkdir()
    (repo / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (admin / "gitdir").write_text("an unrelated file\n", encoding="utf-8")
    assert gitmeta.gitfile_backlink_matches(repo)


def test_canonical_identity_falls_back_when_realpath_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        os.path,
        "realpath",
        lambda _path: (_ for _ in ()).throw(OSError("nope")),
    )
    assert gitmeta.canonical_path_identity(tmp_path) == os.path.normcase(
        os.path.abspath(tmp_path)
    )
