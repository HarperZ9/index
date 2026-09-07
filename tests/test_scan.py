import shutil
import subprocess
import hashlib
import os
from pathlib import Path

from index_graph.cli_handlers._common import repo_paths
from index_graph.config import Config, Rule
from index_graph.scan import build_map, discover_repos


def _make_repo(path: Path):
    (path / ".git").mkdir(parents=True)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_real_repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    _git(path, "config", "user.email", "t@t.t")
    _git(path, "config", "user.name", "t")
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")
    _git(path, "remote", "add", "origin", "https://github.com/example/old.git")
    return path


def _state_line_count(path: Path) -> int:
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def test_discover_prunes_and_sorts(tmp_path: Path):
    _make_repo(tmp_path / "public" / "b")
    _make_repo(tmp_path / "public" / "a")
    (tmp_path / "node_modules" / "pkg" / ".git").mkdir(parents=True)
    (tmp_path / "target" / "debug" / "crate" / ".git").mkdir(parents=True)
    found = [p.relative_to(tmp_path).as_posix() for p in discover_repos(tmp_path, Config())]
    assert found == ["public/a", "public/b"]  # sorted; node_modules pruned


def test_discover_does_not_descend_inside_repo_roots_by_default(tmp_path: Path):
    _make_repo(tmp_path / "public" / "app")
    _make_repo(tmp_path / "public" / "app" / "vendor" / "nested")

    found = [p.relative_to(tmp_path).as_posix() for p in discover_repos(tmp_path, Config())]

    assert found == ["public/app"]


def test_discover_can_opt_into_nested_repos_inside_repo_roots(tmp_path: Path):
    _make_repo(tmp_path / "public" / "app")
    _make_repo(tmp_path / "public" / "app" / "vendor" / "nested")

    found = [
        p.relative_to(tmp_path).as_posix()
        for p in discover_repos(tmp_path, Config(descend_into_repos=True))
    ]

    assert found == ["public/app", "public/app/vendor/nested"]


def test_discover_descends_from_scan_root_even_when_root_is_a_repo(tmp_path: Path):
    _make_repo(tmp_path)
    _make_repo(tmp_path / "public" / "app")
    _make_repo(tmp_path / "public" / "app" / "vendor" / "nested")

    found = [p.relative_to(tmp_path).as_posix() for p in discover_repos(tmp_path, Config())]

    assert found == [".", "public/app"]


def test_repo_paths_preserves_duplicate_basenames_with_relative_keys(tmp_path: Path):
    _make_repo(tmp_path / "public" / "index")
    _make_repo(tmp_path / "protected" / "index")
    _make_repo(tmp_path / "public" / "forum")

    found = repo_paths(tmp_path)

    assert found["forum"] == tmp_path / "public" / "forum"
    assert found["public/index"] == tmp_path / "public" / "index"
    assert found["protected/index"] == tmp_path / "protected" / "index"
    assert len(found) == 3


def test_repo_paths_treats_multi_repo_scan_root_as_container(tmp_path: Path):
    _make_repo(tmp_path)
    _make_repo(tmp_path / "public" / "app")

    found = repo_paths(tmp_path)

    assert found == {"app": tmp_path / "public" / "app"}


def test_repo_paths_can_include_scan_root_when_configured(tmp_path: Path):
    _make_repo(tmp_path)
    _make_repo(tmp_path / "public" / "app")
    (tmp_path / ".index.toml").write_text(
        "[scan]\ninclude_root_repo = true\n",
        encoding="utf-8",
    )

    found = repo_paths(tmp_path)

    assert found[tmp_path.name] == tmp_path
    assert found["app"] == tmp_path / "public" / "app"


def test_repo_paths_includes_root_when_it_is_the_only_repo(tmp_path: Path):
    _make_repo(tmp_path)

    found = repo_paths(tmp_path)

    assert found == {tmp_path.name: tmp_path}


def test_build_map_portable_omits_absolute_paths(tmp_path: Path):
    _make_repo(tmp_path / "public" / "demo")
    result = build_map(tmp_path, Config(rules=(Rule("public/**", "public"),)), "0.2.0")
    encoded = str(result.to_json())
    assert result.absolute_paths_included is False
    assert result.root is None
    assert str(tmp_path) not in encoded
    assert result.repositories[0].path == "public/demo"
    assert result.class_counts == {"public": 1}


def test_build_map_local_includes_absolute_root(tmp_path: Path):
    _make_repo(tmp_path / "demo")
    result = build_map(tmp_path, Config(portable=False), "0.2.0")
    assert result.absolute_paths_included is True
    assert result.root == str(tmp_path.resolve())
    assert result.repositories[0].path == str((tmp_path / "demo").resolve())


def test_omit_origin_classes_blanks_origin(tmp_path: Path):
    _make_repo(tmp_path / "protected" / "secret")
    cfg = Config(rules=(Rule("protected/**", "protected"),),
                 omit_origin_classes=frozenset({"protected"}))
    result = build_map(tmp_path, cfg, "0.2.0")
    assert result.repositories[0].origin == ""


def test_build_map_degrades_when_a_repo_errors(tmp_path: Path, monkeypatch, capsys):
    _make_repo(tmp_path / "demo")
    import index_graph.scan as scan_mod
    def _boom(repo):
        raise RuntimeError("boom")
    monkeypatch.setattr(scan_mod, "repo_metadata", _boom)
    result = build_map(tmp_path, Config(), "0.2.0")
    assert result.repo_count == 1
    assert result.repositories[0].branch == "unknown"
    assert result.repositories[0].class_ == "unknown"
    assert "failed to scan" in capsys.readouterr().err


def test_top_level_skips_unstatable_entry(tmp_path: Path, monkeypatch, capsys):
    _make_repo(tmp_path / "demo")
    (tmp_path / "good.txt").write_text("x", encoding="utf-8")
    real_stat = Path.stat
    def flaky_stat(self, *args, **kwargs):
        if self.name == "good.txt":
            raise PermissionError("nope")
        return real_stat(self, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", flaky_stat)
    result = build_map(tmp_path, Config(), "0.2.0")  # must not raise
    names = [e["name"] for e in result.top_level]
    assert "good.txt" not in names
    assert "skipped top-level entry good.txt" in capsys.readouterr().err


def test_discover_repos_records_skipped_unreadable_directories(tmp_path, monkeypatch):
    # os.walk invokes onerror on an unreadable directory; those repos never
    # enter the scan, so a partial scan must be RECORDED, not swallowed to
    # stderr only. The skipped out-param collects them.
    import index_graph.scan as scan

    def fake_walk(root, onerror=None, **kw):
        if onerror is not None:
            err = OSError("permission denied")
            err.filename = str(Path(root) / "locked-subtree")
            onerror(err)
        return iter(())

    monkeypatch.setattr(scan.os, "walk", fake_walk)
    skipped: list[str] = []
    discover_repos(tmp_path, Config(), skipped=skipped)
    assert any("locked-subtree" in s for s in skipped)


def test_check_verdict_downgrades_on_incomplete_scan():
    from index_graph.cli_handlers.certify import _check_verdict
    # a MATCH must not be issued over a scan silently narrowed by unreadable
    # directories: findings that could not see the whole tree are UNVERIFIABLE
    findings = [{"rule": "scan_incomplete", "detail": "skipped a subtree"}]
    assert _check_verdict(False, [], findings) == "UNVERIFIABLE"


def test_discover_repos_prunes_virtualenv_lib64(tmp_path: Path):
    _make_repo(tmp_path / "public" / "app")
    _make_repo(tmp_path / "scratch" / "broken-venv" / "lib64" / "python" / "vendor")

    found = [p.relative_to(tmp_path).as_posix() for p in discover_repos(tmp_path, Config())]

    assert found == ["public/app"]


def test_discover_repos_stops_on_checkpoint_without_claiming_complete(tmp_path: Path):
    for idx in range(20):
        _make_repo(tmp_path / f"repo-{idx:02d}")

    calls = {"count": 0}

    def checkpoint(_path: Path) -> bool:
        calls["count"] += 1
        return calls["count"] <= 5

    found = discover_repos(tmp_path, Config(), checkpoint=checkpoint)
    rels = [p.relative_to(tmp_path).as_posix() for p in found]

    assert rels
    assert len(rels) < 20
    assert rels == sorted(rels, key=str.lower)


def test_build_map_resume_state_reuses_completed_repo_rows(tmp_path: Path, monkeypatch):
    _make_repo(tmp_path / "a")
    _make_repo(tmp_path / "b")
    state = tmp_path / "map-resume.jsonl"
    import index_graph.scan as scan_mod

    calls: list[str] = []

    def fake_metadata(repo: Path):
        calls.append(repo.name)
        return {
            "branch": f"branch-{repo.name}",
            "head": f"head-{repo.name}",
            "origin": "",
            "dirty_count": 0,
            "untracked_count": 0,
        }

    monkeypatch.setattr(
        scan_mod,
        "_repo_resume_identity",
        lambda repo, root, config, **kwargs: {"repo": repo.name},
    )
    monkeypatch.setattr(scan_mod, "repo_metadata", fake_metadata)
    first = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    assert [row.path for row in first.repositories] == ["a", "b"]
    assert calls == ["a", "b"]
    assert state.exists()

    def fail_metadata(repo: Path):
        raise AssertionError(f"resume state should skip {repo}")

    monkeypatch.setattr(scan_mod, "repo_metadata", fail_metadata)
    second = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    assert [row.branch for row in second.repositories] == ["branch-a", "branch-b"]


def test_build_map_resume_state_ignores_legacy_rows_without_identity(tmp_path: Path, monkeypatch):
    _make_repo(tmp_path / "a")
    state = tmp_path / "map-resume.jsonl"
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    state.write_text(
        f'{{"schema":"index.map-resume-row/v1","root_sha256_prefix":"{root_hash}",'
        '"repo_relative":"a","row":{"path":"a","class":"stale","branch":"old",'
        '"head":"old","origin":"","dirty_count":0,"untracked_count":0,"markers":[]}}\n',
        encoding="utf-8",
    )
    import index_graph.scan as scan_mod

    monkeypatch.setattr(
        scan_mod,
        "_repo_resume_identity",
        lambda repo, root, config, **kwargs: {"repo": repo.name},
    )
    monkeypatch.setattr(
        scan_mod,
        "repo_metadata",
        lambda repo: {
            "branch": "fresh",
            "head": "fresh",
            "origin": "",
            "dirty_count": 0,
            "untracked_count": 0,
        },
    )

    result = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    assert result.repositories[0].branch == "fresh"


def test_build_map_resume_state_writes_and_reuses_clean_real_git_row(tmp_path: Path, monkeypatch):
    _make_real_repo(tmp_path / "repo")
    state = tmp_path / "map-resume.jsonl"
    import index_graph.scan as scan_mod

    calls: list[str] = []
    real_metadata = scan_mod.repo_metadata

    def counted_metadata(repo: Path):
        calls.append(repo.name)
        return real_metadata(repo)

    monkeypatch.setattr(scan_mod, "repo_metadata", counted_metadata)
    first = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)
    first_json = first.repositories[0].to_json()

    second = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    assert calls == ["repo"]
    assert _state_line_count(state) == 1
    assert second.repositories[0].to_json() == first_json


def test_build_map_resume_state_reuses_clean_repo_after_tracked_mtime_churn(tmp_path: Path):
    repo = _make_real_repo(tmp_path / "repo")
    state = tmp_path / "map-resume.jsonl"
    first = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)
    tracked = repo / "README.md"
    before = tracked.stat()

    os.utime(tracked, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
    second = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    assert first.repositories[0].to_json() == second.repositories[0].to_json()
    assert _state_line_count(state) == 1


def test_build_map_resume_state_rebuilds_when_dirty_state_changes(tmp_path: Path):
    repo = _make_real_repo(tmp_path / "repo")
    state = tmp_path / "map-resume.jsonl"
    first = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    second = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    assert first.repositories[0].dirty_count == 0
    assert second.repositories[0].dirty_count == 1
    assert _state_line_count(state) == 2


def test_build_map_resume_state_rebuilds_after_head_branch_and_origin_change(tmp_path: Path):
    repo = _make_real_repo(tmp_path / "repo")
    state = tmp_path / "map-resume.jsonl"
    first = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    _git(repo, "checkout", "-b", "feature")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "feature")
    _git(repo, "remote", "set-url", "origin", "https://github.com/example/new.git")
    second = build_map(tmp_path, Config(jobs=1), "0.2.0", resume_state=state)

    assert second.repositories[0].branch == "feature"
    assert second.repositories[0].head != first.repositories[0].head
    assert second.repositories[0].origin == "https://github.com/example/new.git"
    assert _state_line_count(state) == 2


def test_build_map_resume_state_rebuilds_when_config_changes_class(tmp_path: Path, monkeypatch):
    _make_repo(tmp_path / "app")
    state = tmp_path / "map-resume.jsonl"
    import index_graph.scan as scan_mod

    calls: list[str] = []

    def fake_metadata(repo: Path):
        calls.append(repo.name)
        return {
            "branch": "main",
            "head": "abc1234",
            "origin": "",
            "dirty_count": 0,
            "untracked_count": 0,
        }

    monkeypatch.setattr(scan_mod, "repo_metadata", fake_metadata)
    monkeypatch.setattr(
        scan_mod,
        "_repo_resume_identity",
        lambda repo, root, config, **kwargs: {
            "repo": repo.name,
            "config": scan_mod._config_resume_identity(config),
        },
    )

    first = build_map(
        tmp_path,
        Config(jobs=1, rules=(Rule("app", "old"),)),
        "0.2.0",
        resume_state=state,
    )
    second = build_map(
        tmp_path,
        Config(jobs=1, rules=(Rule("app", "new"),)),
        "0.2.0",
        resume_state=state,
    )

    assert first.repositories[0].class_ == "old"
    assert second.repositories[0].class_ == "new"
    assert calls == ["app", "app"]
    assert _state_line_count(state) == 2


def test_build_map_resume_state_rebuilds_when_marker_set_changes(tmp_path: Path):
    repo = _make_real_repo(tmp_path / "repo")
    state = tmp_path / "map-resume.jsonl"
    cfg = Config(jobs=1, markers=("pyproject.toml",))
    first = build_map(tmp_path, cfg, "0.2.0", resume_state=state)

    (repo / "pyproject.toml").write_text("[project]\nname = \"demo\"\n", encoding="utf-8")
    second = build_map(tmp_path, cfg, "0.2.0", resume_state=state)

    assert first.repositories[0].markers == ()
    assert second.repositories[0].markers == ("pyproject.toml",)
    assert _state_line_count(state) == 2


def test_build_map_resume_state_drops_deleted_repo_and_adds_new_nested_repo(tmp_path: Path):
    _make_repo(tmp_path / "app")
    _make_repo(tmp_path / "old")
    state = tmp_path / "map-resume.jsonl"
    cfg = Config(jobs=1, descend_into_repos=True)
    first = build_map(tmp_path, cfg, "0.2.0", resume_state=state)

    shutil.rmtree(tmp_path / "old")
    _make_repo(tmp_path / "app" / "vendor" / "nested")
    second = build_map(tmp_path, cfg, "0.2.0", resume_state=state)

    assert [row.path for row in first.repositories] == ["app", "old"]
    assert [row.path for row in second.repositories] == ["app", "app/vendor/nested"]


def test_build_map_marks_git_status_failure_unknown(tmp_path: Path, monkeypatch):
    _make_repo(tmp_path / "repo")
    import index_graph.gitmeta as gitmeta

    def fail_status(repo: Path, args: list[str], **kwargs):
        if "status" in args:
            return gitmeta.GitCommandResult(False, "", "timeout")
        return gitmeta.GitCommandResult(True, "", None)

    monkeypatch.setattr(gitmeta, "run_git_checked", fail_status)

    result = build_map(tmp_path, Config(jobs=1), "0.2.0")

    row = result.repositories[0]
    assert row.branch == "unknown"
    assert row.head == "unknown"
    assert row.dirty_count == 0
    assert row.untracked_count == 0
    assert row.metadata_status == "unknown"
    assert row.metadata_error == "GitMetadataError"
    assert result.dirty_count == 0
    assert result.dirty_count_status == "known_only"
    assert result.metadata_status == "partial"
    assert result.metadata_ok_count == 0
    assert result.metadata_unknown_count == 1
    encoded = result.to_json()
    assert encoded["dirty_count"] == 0
    assert encoded["dirty_count_status"] == "known_only"
    assert encoded["metadata_status"] == "partial"
    assert encoded["metadata_unknown_count"] == 1
