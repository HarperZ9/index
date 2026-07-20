from pathlib import Path

from index_graph.cli_handlers._common import repo_paths
from index_graph.config import Config, Rule
from index_graph.scan import build_map, discover_repos


def _make_repo(path: Path):
    (path / ".git").mkdir(parents=True)


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
