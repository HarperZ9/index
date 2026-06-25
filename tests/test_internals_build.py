from pathlib import Path

from index_graph.internals import build_internals


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_internal_cycle_detected(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from . import b\n")
    _write(tmp_path, "pkg/b.py", "from . import a\n")
    g = build_internals(tmp_path, "pkg")
    assert g.repo == "pkg"
    assert any(set(c) == {"pkg/a", "pkg/b"} for c in g.cycles)


def test_fan_in_out_counts(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/hub.py", "x = 1\n")
    _write(tmp_path, "pkg/one.py", "from .hub import x\n")
    _write(tmp_path, "pkg/two.py", "from .hub import x\n")
    g = build_internals(tmp_path, "pkg")
    assert g.fan_in.get("pkg/hub") == 2
    assert g.fan_out.get("pkg/one") == 1


def test_deterministic_ordering(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from .b import x\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")
    g1 = build_internals(tmp_path, "pkg")
    g2 = build_internals(tmp_path, "pkg")
    assert [m.id for m in g1.modules] == [m.id for m in g2.modules]
    assert [(e.from_id, e.to_id) for e in g1.edges] == [(e.from_id, e.to_id) for e in g2.edges]
