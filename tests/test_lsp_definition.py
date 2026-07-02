"""textDocument/definition: resolved jumps come back as a Location; an
unresolved name comes back null; a symbol from a different repo is never
returned. Every jump is evidence-backed file:line, never a guess.
"""
from __future__ import annotations

from index_graph.lsp.server import LSPServer
from index_graph.lsp.symbols_lsp import path_to_uri
from symbol_fixtures import cross_module, simple_module


def _init(server):
    server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    server.handle_request({"jsonrpc": "2.0", "method": "initialized", "params": {}})


def _definition(server, uri, line, character):
    return server.handle_request({
        "jsonrpc": "2.0", "id": 10, "method": "textDocument/definition",
        "params": {"textDocument": {"uri": uri},
                   "position": {"line": line, "character": character}}})


def test_definition_within_module(tmp_path):
    simple_module(tmp_path)
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "mod.py")
    # cursor on "foo()" call (line index 5) jumps to "def foo" (line index 0)
    r = _definition(server, uri, 5, 4)
    loc = r["result"]
    assert loc is not None
    assert loc["uri"] == uri
    assert loc["range"]["start"]["line"] == 0


def test_definition_cross_module_resolved(tmp_path):
    cross_module(tmp_path)
    server = LSPServer(root=tmp_path)
    _init(server)
    app_uri = path_to_uri(tmp_path / "app.py")
    # app.py line index 4 is "    exported()"
    r = _definition(server, app_uri, 4, 4)
    loc = r["result"]
    assert loc is not None
    assert loc["uri"] == path_to_uri(tmp_path / "lib.py")


def test_definition_unresolved_name_returns_null(tmp_path):
    # Negative #2: a call to a name with no definition returns null, not a guess
    (tmp_path / "main.py").write_text("def run():\n    missing()\n", encoding="utf-8")
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "main.py")
    r = _definition(server, uri, 1, 4)  # cursor on "missing()"
    assert r["result"] is None
    assert "error" not in r


def test_definition_cross_repo_isolation(tmp_path):
    # Negative #1: a symbol that exists only in a sibling repo is never returned
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "a.py").write_text("def a_run():\n    only_in_b()\n", encoding="utf-8")
    (repo_b / "b.py").write_text("def only_in_b():\n    pass\n", encoding="utf-8")
    server = LSPServer(root=repo_a)  # server only sees repo_a
    _init(server)
    a_uri = path_to_uri(repo_a / "a.py")
    # cursor on the only_in_b() call in repo_a; the def lives in repo_b
    r = _definition(server, a_uri, 1, 4)
    assert r["result"] is None  # never a cross-repo jump into repo_b


def test_definition_unresolved_call_with_same_named_decoy_returns_null(tmp_path):
    # Negative #2 (the meaningful case): a same-named definition exists in an
    # unrelated file, but the call site under the cursor has NO import/call edge
    # to it -- build_symbol_graph classifies it cross_module_unresolved. The LSP
    # must return null, not a guessed jump to the decoy.
    (tmp_path / "a.py").write_text("def helper():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def run():\n    helper()\n", encoding="utf-8")
    server = LSPServer(root=tmp_path)
    _init(server)
    b_uri = path_to_uri(tmp_path / "b.py")
    # cursor on the unresolved helper() call in b.py (no import of helper)
    r = _definition(server, b_uri, 1, 4)
    assert r["result"] is None  # must not jump to a.py's helper()
    assert "error" not in r


def test_definition_for_document_outside_root_returns_null(tmp_path):
    simple_module(tmp_path)
    server = LSPServer(root=tmp_path)
    _init(server)
    outside = tmp_path.parent / "outside_lsp.py"
    outside.write_text("def foo():\n    pass\n", encoding="utf-8")
    try:
        r = _definition(server, path_to_uri(outside), 0, 4)
        assert r["result"] is None
    finally:
        outside.unlink()
