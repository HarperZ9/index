"""Exact within-module call resolution: AST-derived, evidence-backed, high confidence."""
from index_graph.symbols import build_symbol_graph

from symbol_fixtures import write


def test_function_call_resolved_exactly(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    g = build_symbol_graph(tmp_path)
    foo = next(s for s in g.symbols if s.name == "foo")
    bar = next(s for s in g.symbols if s.name == "bar")
    assert foo.id == "mod::foo"
    assert foo.kind == "function"
    assert foo.file == "mod.py"
    assert foo.line == 1
    call = next(c for c in g.calls if c.from_symbol == bar.id and c.to_name == "foo")
    assert call.to_symbol == foo.id
    assert call.resolution == "exact"
    assert call.confidence == "high"
    assert call.evidence_file == "mod.py"
    assert call.evidence_line == 6


def test_method_call_on_self_is_exact(tmp_path):
    write(tmp_path, "mod.py",
          "class C:\n"
          "    def a(self):\n"
          "        pass\n"
          "    def b(self):\n"
          "        self.a()\n")
    g = build_symbol_graph(tmp_path)
    a = next(s for s in g.symbols if s.name == "a")
    b = next(s for s in g.symbols if s.name == "b")
    assert a.id == "mod::C::a"
    assert a.kind == "method"
    assert a.parent == "mod::C"
    call = next(c for c in g.calls if c.from_symbol == b.id and c.to_name == "a")
    assert call.to_symbol == a.id
    assert call.resolution == "exact"
    assert call.confidence == "high"


def test_class_definition_is_discovered(tmp_path):
    write(tmp_path, "mod.py", "class Widget:\n    pass\n")
    g = build_symbol_graph(tmp_path)
    w = next(s for s in g.symbols if s.name == "Widget")
    assert w.id == "mod::Widget"
    assert w.kind == "class"
    assert w.is_public is True


def test_async_function_kind(tmp_path):
    write(tmp_path, "mod.py", "async def fetch():\n    pass\n")
    g = build_symbol_graph(tmp_path)
    f = next(s for s in g.symbols if s.name == "fetch")
    assert f.kind == "async_function"


def test_private_symbol_flagged(tmp_path):
    write(tmp_path, "mod.py", "def _helper():\n    pass\n")
    g = build_symbol_graph(tmp_path)
    h = next(s for s in g.symbols if s.name == "_helper")
    assert h.is_public is False


def test_undefined_call_is_unresolved_not_guessed(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    undefined_func()\n")
    g = build_symbol_graph(tmp_path)
    calls = [c for c in g.calls if c.from_symbol == "mod::foo"]
    assert len(calls) == 1
    assert calls[0].to_symbol is None
    assert calls[0].to_name == "undefined_func"
    assert calls[0].resolution == "cross_module_unresolved"
    assert calls[0].confidence == "low"


def test_fan_in_out_counts_only_resolved(tmp_path):
    write(tmp_path, "mod.py",
          "def foo():\n    pass\n\n\ndef bar():\n    foo()\n\n\ndef baz():\n    foo()\n")
    g = build_symbol_graph(tmp_path)
    assert g.fan_in.get("mod::foo") == 2
    assert g.fan_out.get("mod::bar") == 1
    assert g.fan_out.get("mod::baz") == 1
