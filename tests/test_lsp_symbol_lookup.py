"""The bridge from an LSP (uri, position) to a wave-1 symbol, and back to a
Location. Position lookup is derived from the AST-exact definition lines, so a
cursor on a definition line resolves to that symbol and nothing else.
"""
from __future__ import annotations

from pathlib import Path

from index_graph.lsp.symbols_lsp import (find_symbol_at_position, path_to_uri,
                                         to_lsp_location, uri_to_path)
from index_graph.symbols import build_symbol_graph
from symbol_fixtures import simple_module


def test_uri_path_roundtrip(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("x = 1\n", encoding="utf-8")
    uri = path_to_uri(p)
    assert uri.startswith("file://")
    assert uri_to_path(uri) == p.resolve()


def test_find_symbol_at_definition_line(tmp_path):
    simple_module(tmp_path)
    g = build_symbol_graph(tmp_path)
    # "def bar():" is line 5 (0-indexed line 4) in the simple_module fixture
    uri = path_to_uri(tmp_path / "mod.py")
    sym = find_symbol_at_position(uri, {"line": 4, "character": 4}, g, tmp_path)
    assert sym is not None
    assert sym.name == "bar"


def test_find_symbol_on_call_line_matches_name_written(tmp_path):
    simple_module(tmp_path)
    g = build_symbol_graph(tmp_path)
    # line 6 (0-indexed 5) is "    foo()" — the cursor is on a call, not a def.
    # The bridge resolves the *word under the cursor* against known symbols.
    uri = path_to_uri(tmp_path / "mod.py")
    sym = find_symbol_at_position(uri, {"line": 5, "character": 4}, g, tmp_path)
    assert sym is not None
    assert sym.name == "foo"


def test_find_symbol_on_blank_line_returns_none(tmp_path):
    simple_module(tmp_path)
    g = build_symbol_graph(tmp_path)
    uri = path_to_uri(tmp_path / "mod.py")
    # line index 3 is a blank separator line
    assert find_symbol_at_position(uri, {"line": 3, "character": 0}, g, tmp_path) is None


def test_find_symbol_for_file_outside_root_returns_none(tmp_path):
    simple_module(tmp_path)
    g = build_symbol_graph(tmp_path)
    other = tmp_path.parent / "elsewhere.py"
    other.write_text("def foo():\n    pass\n", encoding="utf-8")
    try:
        uri = path_to_uri(other)
        assert find_symbol_at_position(uri, {"line": 0, "character": 4}, g, tmp_path) is None
    finally:
        other.unlink()


def test_to_lsp_location_is_zero_indexed_line(tmp_path):
    simple_module(tmp_path)
    g = build_symbol_graph(tmp_path)
    bar = next(s for s in g.symbols if s.name == "bar")
    loc = to_lsp_location(bar, tmp_path)
    assert loc["uri"] == path_to_uri(tmp_path / "mod.py")
    # SymbolDefinition.line is 1-indexed; LSP is 0-indexed
    assert loc["range"]["start"]["line"] == bar.line - 1
