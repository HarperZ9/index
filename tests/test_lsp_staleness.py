"""Staleness: a workspace that changed on disk after initialize is detected,
not silently answered from a stale graph. This is can-it-FAIL negative #3.
"""
from __future__ import annotations

from index_graph.lsp.server import LSPServer, STALE_CODE
from index_graph.lsp.symbols_lsp import path_to_uri
from symbol_fixtures import write


def _init(server):
    server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    server.handle_request({"jsonrpc": "2.0", "method": "initialized", "params": {}})


def test_fingerprint_stable_when_nothing_changes(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    assert server.is_stale() is False
    assert server.is_stale() is False  # idempotent


def test_unchanged_tree_does_not_full_reread_per_request(tmp_path, monkeypatch):
    # Perf guard: on an unchanged tree, the cheap stat-only pre-check must take
    # the fast path so the expensive full-content fingerprint is NOT recomputed
    # on every definition/references request (IDEs issue these constantly).
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)  # the single build computes the full fingerprint exactly once
    import index_graph.lsp.server as srv
    real = srv._fingerprint
    calls = {"n": 0}

    def counting(root):
        calls["n"] += 1
        return real(root)

    monkeypatch.setattr(srv, "_fingerprint", counting)
    for _ in range(25):
        assert server.is_stale() is False
    assert calls["n"] == 0, (
        f"the full-content fingerprint was recomputed {calls['n']} times on an "
        "unchanged tree; the cheap pre-check should take the fast path")


def test_definition_on_stale_workspace_errors(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "mod.py")
    # user edits the file on disk, outside the LSP protocol
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    baz()\n")
    r = server.handle_request({
        "jsonrpc": "2.0", "id": 10, "method": "textDocument/definition",
        "params": {"textDocument": {"uri": uri}, "position": {"line": 3, "character": 4}}})
    assert "error" in r
    assert r["error"]["code"] == STALE_CODE
    assert "stale" in r["error"]["message"].lower() or "chang" in r["error"]["message"].lower()


def test_references_on_stale_workspace_errors(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "mod.py")
    write(tmp_path, "new.py", "def added():\n    pass\n")  # a new file appears
    r = server.handle_request({
        "jsonrpc": "2.0", "id": 11, "method": "textDocument/references",
        "params": {"textDocument": {"uri": uri}, "position": {"line": 0, "character": 4},
                   "context": {"includeDeclaration": False}}})
    assert "error" in r
    assert r["error"]["code"] == STALE_CODE


def test_reinitialize_clears_staleness(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n    foo()\n")
    assert server.is_stale() is True
    # IDE re-initializes; the graph and fingerprint are rebuilt fresh
    _init(server)
    assert server.is_stale() is False
