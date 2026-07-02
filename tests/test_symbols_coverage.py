"""Parse errors and dynamic dispatch are recorded honestly, never guessed."""
from index_graph.symbols import build_symbol_graph

from symbol_fixtures import write


def test_parse_error_is_a_coverage_gap(tmp_path):
    write(tmp_path, "good.py", "def foo():\n    pass\n")
    write(tmp_path, "bad.py", "def this is not python!\n")
    g = build_symbol_graph(tmp_path)
    assert "bad.py" in g.coverage.parse_errors
    assert any(s.name == "foo" for s in g.symbols)  # good.py still discovered


def test_getattr_dynamic_call_is_flagged_not_guessed(tmp_path):
    write(tmp_path, "mod.py",
          "def foo():\n"
          "    m = getattr(obj, 'name')\n"
          "    m()\n")
    g = build_symbol_graph(tmp_path)
    # the dynamic call site is recorded as a coverage gap; nothing is invented
    assert g.coverage.dynamic_calls
    assert not any(c.resolution == "exact" and c.from_symbol == "mod::foo"
                   for c in g.calls)


def test_coverage_complete_on_clean_module(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    g = build_symbol_graph(tmp_path)
    assert not g.coverage.parse_errors
