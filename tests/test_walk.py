from __future__ import annotations

from index_graph.graph.walk import EXCLUDE_DIRS, walk_files


def _make(root):
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "buried.py").write_text("y = 2\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "dep.js").write_text("z\n", encoding="utf-8")
    (root / "pkg" / "__main__.py").write_text("main\n", encoding="utf-8")


def test_walk_prunes_excluded_dirs_by_suffix(tmp_path):
    _make(tmp_path)
    found = {p.name for p in walk_files(tmp_path, suffixes=(".py",))}
    assert "a.py" in found
    assert "buried.py" not in found          # under .venv -> pruned
    assert ".venv" in EXCLUDE_DIRS and "node_modules" in EXCLUDE_DIRS


def test_walk_matches_by_exact_name(tmp_path):
    _make(tmp_path)
    found = {p.name for p in walk_files(tmp_path, names=("__main__.py",))}
    assert found == {"__main__.py"}


def test_walk_missing_root_is_empty_not_error(tmp_path):
    assert list(walk_files(tmp_path / "does-not-exist", suffixes=(".py",))) == []
