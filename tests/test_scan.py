from pathlib import Path

from workspace_repo_map.config import Config, Rule
from workspace_repo_map.scan import build_map, discover_repos


def _make_repo(path: Path):
    (path / ".git").mkdir(parents=True)


def test_discover_prunes_and_sorts(tmp_path: Path):
    _make_repo(tmp_path / "public" / "b")
    _make_repo(tmp_path / "public" / "a")
    (tmp_path / "node_modules" / "pkg" / ".git").mkdir(parents=True)
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
    import workspace_repo_map.scan as scan_mod
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
