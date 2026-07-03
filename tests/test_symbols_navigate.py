"""Symbol-graph navigation: go-to-definition, find-references, find-implementations.

Each assertion pins the exact file:line evidence a hop carries and the honest
resolution posture (unresolved refs are never callers; external bases are never
implementation edges).
"""
from index_graph.symbols import (build_symbol_navigator, find_definitions,
                                 find_implementations, find_references)

from symbol_fixtures import inheritance, write


def test_go_to_definition_reports_file_line(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    graph, _ = build_symbol_navigator(tmp_path)
    defs = find_definitions(graph, "foo")
    assert len(defs) == 1
    assert defs[0]["id"] == "mod::foo"
    assert defs[0]["file"] == "mod.py"
    assert defs[0]["line"] == 1
    assert defs[0]["kind"] == "function"


def test_go_to_definition_by_class_method_tail(tmp_path):
    inheritance(tmp_path)
    graph, _ = build_symbol_navigator(tmp_path)
    # A `Class::method` tail resolves against the full id.
    defs = find_definitions(graph, "Animal::speak")
    assert [d["id"] for d in defs] == ["base::Animal::speak"]
    assert defs[0]["file"] == "base.py"
    assert defs[0]["line"] == 2


def test_find_references_resolved_caller_with_evidence(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    graph, _ = build_symbol_navigator(tmp_path)
    result = find_references(graph, "mod::foo")
    assert len(result["references"]) == 1
    ref = result["references"][0]
    assert ref["from_symbol"] == "mod::bar"
    assert ref["file"] == "mod.py"
    assert ref["line"] == 6
    assert ref["resolution"] == "exact"
    assert ref["confidence"] == "high"


def test_find_references_unresolved_is_never_a_caller(tmp_path):
    # d.speak() is an attribute call on a plain variable: statically unbindable.
    inheritance(tmp_path)
    write(tmp_path, "use.py",
          "from dog import Dog\n\n\ndef run():\n    d = Dog()\n    d.speak()\n")
    graph, _ = build_symbol_navigator(tmp_path)
    result = find_references(graph, "Dog::speak")
    assert result["references"] == []          # never guessed into a caller
    unresolved = result["unresolved"]
    assert any(u["from_symbol"] == "use::run" and u["file"] == "use.py"
               and u["line"] == 6 for u in unresolved)


def test_find_implementations_class_returns_subclasses(tmp_path):
    inheritance(tmp_path)
    graph, edges = build_symbol_navigator(tmp_path)
    impls = find_implementations(graph, edges, "Animal")
    children = {(s["child"], s["file"], s["line"]) for s in impls["subclasses"]}
    assert ("cat::Cat", "cat.py", 4) in children
    assert ("dog::Dog", "dog.py", 4) in children
    assert impls["overrides"] == []            # a class query yields no method edges
    assert all(s["resolution"] == "cross_module" for s in impls["subclasses"])


def test_find_implementations_method_returns_overrides(tmp_path):
    inheritance(tmp_path)
    graph, edges = build_symbol_navigator(tmp_path)
    impls = find_implementations(graph, edges, "Animal::speak")
    overs = {(o["child"], o["file"], o["line"]) for o in impls["overrides"]}
    assert ("cat::Cat::speak", "cat.py", 5) in overs
    assert ("dog::Dog::speak", "dog.py", 5) in overs
    assert impls["subclasses"] == []


def test_find_implementations_unoverridden_method_is_empty(tmp_path):
    # Animal.legs is defined but no subclass overrides it: zero implementations,
    # honestly, rather than a guessed match.
    inheritance(tmp_path)
    graph, edges = build_symbol_navigator(tmp_path)
    impls = find_implementations(graph, edges, "Animal::legs")
    assert impls["overrides"] == []
    assert impls["subclasses"] == []


def test_external_base_yields_no_implementation_edge(tmp_path):
    # Subclassing an external/unbindable base (not defined in this repo) is
    # never turned into an inheritance edge.
    write(tmp_path, "ext.py",
          "class Widget(SomeExternalBase):\n"
          "    def render(self):\n"
          "        pass\n")
    graph, edges = build_symbol_navigator(tmp_path)
    assert edges == []
    impls = find_implementations(graph, edges, "render")
    assert impls["overrides"] == []
    assert impls["subclasses"] == []


def test_same_module_base_resolves_exact(tmp_path):
    write(tmp_path, "m.py",
          "class Base:\n"
          "    def go(self):\n"
          "        pass\n\n\n"
          "class Sub(Base):\n"
          "    def go(self):\n"
          "        return 1\n")
    graph, edges = build_symbol_navigator(tmp_path)
    impls = find_implementations(graph, edges, "Base::go")
    assert len(impls["overrides"]) == 1
    over = impls["overrides"][0]
    assert over["child"] == "m::Sub::go"
    assert over["file"] == "m.py"
    assert over["line"] == 7
    assert over["resolution"] == "exact"


def test_navigator_is_deterministic(tmp_path):
    inheritance(tmp_path)
    g1, e1 = build_symbol_navigator(tmp_path)
    g2, e2 = build_symbol_navigator(tmp_path)
    assert e1 == e2
    assert [s.id for s in g1.symbols] == [s.id for s in g2.symbols]
