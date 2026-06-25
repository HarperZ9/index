from pathlib import Path

from index_graph.internals import build_internals


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_clean_repo_is_complete(tmp_path):
    _w(tmp_path, "pkg/__init__.py", "")
    _w(tmp_path, "pkg/a.py", "from .b import x\n")
    _w(tmp_path, "pkg/b.py", "x = 1\n")
    cov = build_internals(tmp_path, "pkg").coverage
    assert cov.complete is True
    assert cov.parse_errors == ()
    assert cov.dynamic_imports == ()
    assert cov.modules == 3


def test_parse_error_is_reported(tmp_path):
    _w(tmp_path, "pkg/__init__.py", "")
    _w(tmp_path, "pkg/broken.py", "def (:\n")  # invalid syntax
    cov = build_internals(tmp_path, "pkg").coverage
    assert cov.complete is False
    assert "pkg/broken.py" in cov.parse_errors


def test_python_dynamic_import_is_reported(tmp_path):
    _w(tmp_path, "pkg/__init__.py", "")
    _w(tmp_path, "pkg/a.py", "import importlib\nm = importlib.import_module('x')\n")
    cov = build_internals(tmp_path, "pkg").coverage
    assert cov.complete is False
    assert any(f == "pkg/a.py" for f, _ in cov.dynamic_imports)


def test_dunder_import_is_dynamic(tmp_path):
    _w(tmp_path, "pkg/__init__.py", "")
    _w(tmp_path, "pkg/a.py", "x = __import__('os')\n")
    cov = build_internals(tmp_path, "pkg").coverage
    assert any(f == "pkg/a.py" for f, _ in cov.dynamic_imports)


def test_js_dynamic_require_is_reported(tmp_path):
    _w(tmp_path, "src/a.js", "const name = 'x';\nconst m = require(name);\n")
    cov = build_internals(tmp_path, "app").coverage
    assert cov.complete is False
    assert any(f == "src/a.js" for f, _ in cov.dynamic_imports)
