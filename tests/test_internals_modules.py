from pathlib import Path

from index_graph.internals.modules import discover_modules, extract_internal_edges


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_discovers_python_modules_with_ids(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "x = 1\n")
    _write(tmp_path, "pkg/sub/b.py", "y = 2\n")
    mods = discover_modules(tmp_path)
    ids = sorted(m.id for m in mods)
    assert ids == ["pkg/__init__", "pkg/a", "pkg/sub/b"]
    assert all(m.language == "python" for m in mods)


def test_relative_import_makes_internal_edge(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from .b import thing\n")
    _write(tmp_path, "pkg/b.py", "thing = 1\n")
    mods = discover_modules(tmp_path)
    edges = extract_internal_edges(tmp_path, mods)
    pairs = {(e.from_id, e.to_id) for e in edges}
    assert ("pkg/a", "pkg/b") in pairs
    e = next(e for e in edges if e.from_id == "pkg/a")
    assert e.evidence_file == "pkg/a.py"
    assert e.evidence_line == 1


def test_absolute_internal_import_resolves(tmp_path):
    _write(tmp_path, "app/__init__.py", "")
    _write(tmp_path, "app/main.py", "import app.helpers\n")
    _write(tmp_path, "app/helpers.py", "def h(): pass\n")
    mods = discover_modules(tmp_path)
    edges = extract_internal_edges(tmp_path, mods)
    assert ("app/main", "app/helpers") in {(e.from_id, e.to_id) for e in edges}


def test_external_import_is_not_internal_edge(tmp_path):
    _write(tmp_path, "app/__init__.py", "")
    _write(tmp_path, "app/main.py", "import os\nimport requests\n")
    mods = discover_modules(tmp_path)
    edges = extract_internal_edges(tmp_path, mods)
    assert edges == []
