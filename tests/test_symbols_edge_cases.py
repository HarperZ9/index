"""Edge cases: same-name redefinition must not silently collide on symbol id,
and class-method mapping stays correct regardless of the extraction path.

These guard two review findings: (1) two top-level `def foo` in one module
produced two SymbolDefinitions with an identical id, which silently collided in
the wiki page map and downstream resolution; (2) the class-method map must
resolve `self.m()` correctly even when several classes and methods coexist.
"""
from index_graph.symbols import build_symbol_graph, symbol_graph_to_payload
from index_graph.certify import canonical_sha

from symbol_fixtures import write


def test_redefined_top_level_symbol_has_unique_ids(tmp_path):
    """Two `def foo` at module scope must not yield two definitions sharing an id.

    Python runtime keeps the last binding; the static graph keeps exactly one
    definition per id so the wiki page map and resolution are unambiguous.
    """
    write(tmp_path, "mod.py",
          "def foo():\n"
          "    pass\n"
          "\n\n"
          "def foo():\n"          # redefinition, same name, module scope
          "    pass\n"
          "\n\n"
          "def caller():\n"
          "    foo()\n")
    g = build_symbol_graph(tmp_path)
    foo_defs = [s for s in g.symbols if s.name == "foo"]
    assert len(foo_defs) == 1, "redefinition must collapse to one definition per id"
    ids = [s.id for s in g.symbols]
    assert len(ids) == len(set(ids)), "no two definitions may share an id"
    # the live definition is the last `def foo` (runtime semantics)
    assert foo_defs[0].line == 5


def test_redefinition_graph_is_byte_stable(tmp_path):
    write(tmp_path, "mod.py",
          "def foo():\n    pass\n\n\ndef foo():\n    pass\n\n\ndef caller():\n    foo()\n")
    g1 = build_symbol_graph(tmp_path)
    g2 = build_symbol_graph(tmp_path)
    assert canonical_sha(symbol_graph_to_payload(g1)) == canonical_sha(symbol_graph_to_payload(g2))


def test_self_method_resolves_across_multiple_classes(tmp_path):
    """Guards the class-method map: self.m() resolves to the *enclosing* class's
    method, not a same-named method on another class."""
    write(tmp_path, "mod.py",
          "class A:\n"
          "    def helper(self):\n"
          "        pass\n"
          "    def run(self):\n"
          "        self.helper()\n"
          "class B:\n"
          "    def helper(self):\n"
          "        pass\n"
          "    def go(self):\n"
          "        self.helper()\n")
    g = build_symbol_graph(tmp_path)
    a_run = next(c for c in g.calls if c.from_symbol == "mod::A::run")
    b_go = next(c for c in g.calls if c.from_symbol == "mod::B::go")
    assert a_run.to_symbol == "mod::A::helper"
    assert a_run.resolution == "exact"
    assert b_go.to_symbol == "mod::B::helper"
    assert b_go.resolution == "exact"
