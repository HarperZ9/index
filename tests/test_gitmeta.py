import subprocess
from pathlib import Path

from workspace_repo_map.gitmeta import repo_metadata, run_git, sanitize_credentials


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
