"""Cross-module resolution is best-effort and honestly labeled, never guessed."""
from index_graph.symbols import build_symbol_graph

from symbol_fixtures import write


def test_cross_module_call_via_import_is_moderate(tmp_path):
    write(tmp_path, "lib.py", "def exported():\n    pass\n")
    write(tmp_path, "app.py",
          "from lib import exported\n\n\ndef main():\n    exported()\n")
    g = build_symbol_graph(tmp_path)
    call = next(c for c in g.calls if c.from_symbol == "app::main" and c.to_name == "exported")
    assert call.to_symbol == "lib::exported"
    assert call.resolution == "cross_module"
    assert call.confidence == "moderate"


def test_cross_module_only_when_import_edge_and_definition_exist(tmp_path):
    # imported name that does not resolve to any real definition stays unresolved
    write(tmp_path, "lib.py", "x = 1\n")
    write(tmp_path, "app.py",
          "from lib import missing_name\n\n\ndef main():\n    missing_name()\n")
    g = build_symbol_graph(tmp_path)
    call = next(c for c in g.calls if c.from_symbol == "app::main")
    assert call.to_symbol is None
    assert call.resolution == "cross_module_unresolved"


def test_attribute_call_on_imported_object_is_unresolved(tmp_path):
    write(tmp_path, "lib.py", "class Foo:\n    pass\n")
    write(tmp_path, "app.py",
          "from lib import Foo\n\n\ndef main():\n    obj = Foo()\n    obj.unknown_method()\n")
    g = build_symbol_graph(tmp_path)
    attr = [c for c in g.calls if c.to_name == "unknown_method"]
    assert attr
    assert attr[0].to_symbol is None
    assert attr[0].resolution == "cross_module_unresolved"


def test_within_module_wins_over_cross_module(tmp_path):
    # a local definition shadows an import of the same name: local resolution
    write(tmp_path, "lib.py", "def foo():\n    pass\n")
    write(tmp_path, "app.py",
          "from lib import foo\n\n\ndef foo():\n    pass\n\n\ndef main():\n    foo()\n")
    g = build_symbol_graph(tmp_path)
    call = next(c for c in g.calls if c.from_symbol == "app::main" and c.to_name == "foo")
    assert call.to_symbol == "app::foo"
    assert call.resolution == "exact"
