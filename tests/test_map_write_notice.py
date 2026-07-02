"""The default map write is explicit: a one-line notice of the write path
before anything touches the filesystem, and --dry-run reports the would-be
write without writing. The negative fixture: a dry run that leaves ANY new
file behind must fail."""
from pathlib import Path

import pytest

import index_graph.cli as cli
from index_graph.cli import main


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "demo" / ".git").mkdir(parents=True)
    return tmp_path


def _tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def test_map_prints_write_notice_naming_the_path(tmp_path, capsys):
    root = _workspace(tmp_path)
    assert main(["--root", str(root)]) == 0
    out = capsys.readouterr().out.splitlines()
    expected = root.resolve() / "INDEX.json"
    assert out[0] == f"index map: writing {expected}"
    assert out[1] == f"wrote {expected}"  # existing lines preserved
    assert (root / "INDEX.json").exists()


def test_map_notice_is_printed_before_the_write(tmp_path, capsys, monkeypatch):
    root = _workspace(tmp_path)

    def _interrupted(*args, **kwargs):
        raise RuntimeError("write interrupted")

    monkeypatch.setattr(cli, "write_map", _interrupted)
    with pytest.raises(RuntimeError):
        main(["--root", str(root)])
    out = capsys.readouterr().out
    assert f"index map: writing {root.resolve() / 'INDEX.json'}" in out
    assert not (root / "INDEX.json").exists()


def test_dry_run_reports_the_path_and_writes_nothing(tmp_path, capsys):
    root = _workspace(tmp_path)
    before = _tree(root)
    assert main(["--root", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"index map: would write {root.resolve() / 'INDEX.json'}" in out
    assert "dry-run" in out
    assert "repos=1" in out
    assert not (root / "INDEX.json").exists()
    # negative fixture: a dry run that creates ANY new file fails here
    assert _tree(root) == before


def test_map_subcommand_dry_run_with_explicit_output(tmp_path, capsys):
    root = _workspace(tmp_path)
    target = tmp_path / "out" / "inventory.json"
    before = _tree(tmp_path)
    assert main(["map", "--root", str(root),
                 "--output", str(target), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"index map: would write {target.resolve()}" in out
    assert not target.exists()
    assert _tree(tmp_path) == before


def test_dry_run_rejects_json_mode(tmp_path):
    root = _workspace(tmp_path)
    with pytest.raises(SystemExit):
        main(["--root", str(root), "--json", "--dry-run"])
