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


def test_unreadable_file_is_a_coverage_gap_not_silently_dropped(tmp_path, monkeypatch):
    # a .py file that walk_files yields but that raises OSError on read
    # (locked / permission-denied / removed mid-scan) must dent coverage,
    # not vanish while coverage.complete still reports True.
    import index_graph.symbols.definitions as d
    write(tmp_path, "ok.py", "def foo():\n    pass\n")
    write(tmp_path, "locked.py", "def bar():\n    pass\n")
    real_read = d.Path.read_text

    def flaky(self, *a, **k):
        if self.name == "locked.py":
            raise OSError("permission denied")
        return real_read(self, *a, **k)

    monkeypatch.setattr(d.Path, "read_text", flaky)
    defs, parse_errors = d.extract_symbol_definitions(tmp_path)
    assert "locked.py" in parse_errors
    # and the module graph's coverage reflects it (complete drops)
    g = build_symbol_graph(tmp_path)
    assert "locked.py" in g.coverage.parse_errors
