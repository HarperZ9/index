import os
import subprocess
from pathlib import Path

import pytest

from index_graph.config import Config, Rule
import index_graph.scan as scan_mod
from index_graph.scan import build_map, discover_repos


def _make_repo(path: Path):
    (path / ".git").mkdir(parents=True)


def _make_directory_alias(alias: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"junction creation unavailable: {result.stderr}")
    else:
        alias.symlink_to(target, target_is_directory=True)


def _linked_worktree_and_copy(root: Path) -> tuple[Path, Path, Path]:
    main = root / "main"
    admin = main / ".git" / "worktrees" / "feature"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n", encoding="utf-8")
    linked = root / "worktrees" / "feature"
    linked.mkdir(parents=True)
    (linked / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (admin / "gitdir").write_text(f"{linked / '.git'}\n", encoding="utf-8")
    copied = root / "audit" / "source"
    copied.mkdir(parents=True)
    (copied / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    return main, linked, copied


def test_deduplicate_repo_aliases_prefers_direct_path(tmp_path: Path):
    target = tmp_path / "z-target"
    _make_repo(target)
    alias = tmp_path / "a-alias"
    _make_directory_alias(alias, target)
    assert scan_mod.deduplicate_repo_aliases([alias, target]) == [target]


def test_deduplicate_repo_aliases_keeps_sole_alias(tmp_path: Path):
    target = tmp_path / "target"
    _make_repo(target)
    alias = tmp_path / "alias"
    _make_directory_alias(alias, target)
    assert scan_mod.deduplicate_repo_aliases([alias]) == [alias]


def test_discover_reports_sole_directory_symlink_alias(tmp_path: Path):
    if os.name == "nt":
        pytest.skip("directory symlink behavior covered on POSIX; Windows uses junction fixture")
    target = tmp_path / "outside" / "target"
    _make_repo(target)
    alias = tmp_path / "scan-root" / "alias"
    alias.parent.mkdir()
    alias.symlink_to(target, target_is_directory=True)
    assert discover_repos(alias.parent, Config()) == [alias]


def test_discover_prunes_directory_symlink_repo_alias(tmp_path: Path):
    if os.name == "nt":
        pytest.skip("directory symlink behavior covered on POSIX; Windows uses junction fixture")
    target = tmp_path / "outside" / "target"
    _make_repo(target)
    alias = tmp_path / "scan-root" / "node_modules"
    alias.parent.mkdir()
    alias.symlink_to(target, target_is_directory=True)
    assert discover_repos(alias.parent, Config()) == []


def test_deduplicate_repo_aliases_collapses_mocked_physical_identity(
    tmp_path: Path, monkeypatch
):
    direct = tmp_path / "direct"
    alias = tmp_path / "alias"
    _make_repo(direct)
    _make_repo(alias)
    monkeypatch.setattr(scan_mod, "canonical_path_identity", lambda _path: "same")
    monkeypatch.setattr(
        scan_mod,
        "_alias_rank",
        lambda path: (path == alias, str(path).casefold(), str(path)),
    )
    assert scan_mod.deduplicate_repo_aliases([alias, direct]) == [direct]


def test_discover_skips_copied_worktree_gitfile(tmp_path: Path):
    main, linked, _ = _linked_worktree_and_copy(tmp_path)
    assert discover_repos(tmp_path, Config()) == [main, linked]


def test_discover_warns_when_copied_worktree_gitfile_is_skipped(tmp_path: Path, capsys):
    _linked_worktree_and_copy(tmp_path)
    discover_repos(tmp_path, Config())
    warning = capsys.readouterr().err
    assert "skipped unregistered linked-worktree copy audit/source" in warning
    assert "git worktree repair" in warning


def test_discover_reports_physical_repo_tree_once(tmp_path: Path):
    target = tmp_path / "z-target"
    _make_repo(target)
    _make_repo(target / "nested")
    alias = tmp_path / "a-alias"
    _make_directory_alias(alias, target)
    found = [path.relative_to(tmp_path).as_posix() for path in discover_repos(tmp_path, Config())]
    assert found == ["z-target", "z-target/nested"]


def test_build_map_does_not_double_count_physical_alias_dirty_state(
    tmp_path: Path, monkeypatch
):
    direct = tmp_path / "direct"
    subprocess.run(["git", "init", "-b", "main", str(direct)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(direct), "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", str(direct), "config", "user.name", "t"], check=True)
    tracked = direct / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(direct), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(direct), "commit", "-m", "initial"], check=True, capture_output=True)
    tracked.write_text("after\n", encoding="utf-8")

    alias = tmp_path / "alias"
    _make_repo(alias)
    monkeypatch.setattr(scan_mod, "canonical_path_identity", lambda _path: "same")
    monkeypatch.setattr(
        scan_mod,
        "_alias_rank",
        lambda path: (path == alias, str(path).casefold(), str(path)),
    )

    result = build_map(tmp_path, Config(), "test")
    assert result.repo_count == 1
    assert result.dirty_count == 1


def test_discover_prunes_and_sorts(tmp_path: Path):
    _make_repo(tmp_path / "public" / "b")
    _make_repo(tmp_path / "public" / "a")
    (tmp_path / "node_modules" / "pkg" / ".git").mkdir(parents=True)
    (tmp_path / "target" / "debug" / "crate" / ".git").mkdir(parents=True)
    found = [p.relative_to(tmp_path).as_posix() for p in discover_repos(tmp_path, Config())]
    assert found == ["public/a", "public/b"]  # sorted; node_modules pruned


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
