import subprocess
from pathlib import Path

import pytest

from index_graph.gitmeta import GitMetadataError, repo_metadata, run_git, sanitize_credentials


def test_sanitize_redacts_userinfo_but_keeps_host():
    assert sanitize_credentials("https://tok@github.com/o/r.git") == \
        "https://<redacted>@github.com/o/r.git"


def test_sanitize_redacts_secret_query():
    assert sanitize_credentials("https://example.com/r.git?token=abc") == \
        "https://example.com/r.git?token=<redacted>"


def test_sanitize_leaves_ssh_user_alone():
    assert sanitize_credentials("git@github.com:o/r.git") == "git@github.com:o/r.git"


def test_sanitize_keeps_a_scheme_ssh_username_too():
    """ssh://git@host names a user and carries nothing secret. Redacting it
    would cost a reader the half of the URL that tells them how the clone was
    set up, and buy nothing."""
    for origin in ("ssh://git@github.com/o/r.git", "ssh://git@host:22/o/r.git"):
        assert sanitize_credentials(origin) == origin


@pytest.mark.parametrize("origin", [
    "ssh://user:pw@host/o/r.git",
    "ssh://user:pw@host:22/o/r.git",
    "git+ssh://user:pw@host/o/r.git",
])
def test_sanitize_redacts_a_password_whatever_the_scheme(origin):
    """The userinfo rule above is bound to http and https, where the token
    usually sits in the user slot alone. A colon says a password came with the
    username, and that is a secret under any scheme."""
    clean = sanitize_credentials(origin)
    assert "pw" not in clean
    assert clean.startswith(origin.split("//")[0] + "//<redacted>@")
    assert clean.endswith("/o/r.git")


@pytest.mark.parametrize("name", [
    "token", "password", "secret", "api_key", "api-key", "API-KEY",
    "access_token", "refresh_token", "client_secret", "X-Api-Key",
])
def test_sanitize_redacts_a_parameter_name_that_arrives_prefixed(name):
    """A word boundary cannot match between an underscore and a letter, so a
    pattern anchored on one sees token and misses access_token. Prefixed names
    are the common ones."""
    assert sanitize_credentials(f"https://h/r.git?{name}=v") ==         f"https://h/r.git?{name}=<redacted>"


@pytest.mark.parametrize("origin", [
    "https://github.com/o/r.git",
    "https://github.com/o/token-store.git",
    "https://github.com/o/r.git?ref=main",
    "file:///srv/git/r.git",
    "/srv/git/r.git",
    "",
])
def test_sanitize_leaves_an_origin_holding_no_credential_alone(origin):
    """Redaction that fires on an ordinary remote makes the map less useful
    without making it safer, and the word token in a repository name is not a
    credential."""
    assert sanitize_credentials(origin) == origin


def test_repo_metadata_raises_when_status_is_unavailable(tmp_path: Path):
    with pytest.raises(GitMetadataError):
        repo_metadata(tmp_path)


def test_repo_metadata_does_not_climb_to_parent_repo_for_broken_nested_marker(tmp_path: Path):
    parent = tmp_path / "parent"
    subprocess.run(["git", "init", "-b", "main", str(parent)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(parent), "config", "user.email", "t@t.t"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(parent), "config", "user.name", "t"],
                   check=True, capture_output=True)
    (parent / "README.md").write_text("parent\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(parent), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(parent), "commit", "-m", "parent"],
                   check=True, capture_output=True)
    broken = parent / "nested" / "broken"
    (broken / ".git").mkdir(parents=True)

    with pytest.raises(GitMetadataError):
        repo_metadata(broken)


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
    assert meta["metadata_status"] == "ok"
    assert meta["status_signature"]


def test_repo_metadata_uses_global_no_optional_locks(monkeypatch, tmp_path):
    calls = []

    def _run(args, **kwargs):
        calls.append(args)
        if args[-3:] == ["config", "--get", "remote.origin.url"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="# branch.oid abcdef1234567890\n# branch.head main\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _run)

    meta = repo_metadata(tmp_path)

    assert meta["branch"] == "main"
    assert calls[0][:4] == ["git", "--no-optional-locks", "-C", str(tmp_path)]
    assert calls[0][4] == "status"


def test_run_git_timeout_returns_empty(monkeypatch, tmp_path):
    import subprocess
    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=5)
    monkeypatch.setattr(subprocess, "run", _raise)
    assert run_git(tmp_path, ["status"]) == ""


def test_run_git_uses_bounded_timeout(monkeypatch, tmp_path):
    seen = {}

    def _run(*args, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, stdout="ok\n", stderr="")

    monkeypatch.delenv("INDEX_GIT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(subprocess, "run", _run)

    assert run_git(tmp_path, ["status"]) == "ok"
    assert seen["timeout"] <= 5
