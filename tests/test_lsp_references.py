"""textDocument/references: every resolved caller of the symbol under the
cursor, each an evidence-backed Location. Unresolved references are never
surfaced as a caller (they are not evidence-backed edges).
"""
from __future__ import annotations

from index_graph.lsp.server import LSPServer
from index_graph.lsp.symbols_lsp import path_to_uri
from symbol_fixtures import simple_module, write


def _init(server):
    server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    server.handle_request({"jsonrpc": "2.0", "method": "initialized", "params": {}})


def _references(server, uri, line, character, include_decl=False):
    return server.handle_request({
        "jsonrpc": "2.0", "id": 20, "method": "textDocument/references",
        "params": {"textDocument": {"uri": uri},
                   "position": {"line": line, "character": character},
                   "context": {"includeDeclaration": include_decl}}})


def test_references_finds_resolved_caller(tmp_path):
    simple_module(tmp_path)  # bar() calls foo()
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "mod.py")
    # cursor on "def foo" (line index 0): who calls foo?
    r = _references(server, uri, 0, 4)
    locs = r["result"]
    assert isinstance(locs, list)
    assert len(locs) == 1
    # the caller site is the "    foo()" line (index 5)
    assert locs[0]["range"]["start"]["line"] == 5


def test_references_excludes_unresolved(tmp_path):
    # foo is called with a real def (resolved) AND a same-named-but-unbound
    # call must not exist; here we assert only resolved callers come back.
    write(tmp_path, "mod.py",
          "def foo():\n    pass\n\n\ndef bar():\n    foo()\n\n\ndef baz():\n    nope()\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "mod.py")
    # references of "nope" (unresolved) -> empty, never a false caller
    r = _references(server, uri, 9, 4)  # cursor on "    nope()"
    assert r["result"] == []


def test_references_empty_for_uncalled_symbol(tmp_path):
    write(tmp_path, "mod.py", "def lonely():\n    pass\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "mod.py")
    r = _references(server, uri, 0, 4)
    assert r["result"] == []
