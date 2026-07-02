"""LSP lifecycle: initialize advertises the two capabilities, initialized
builds the graph, shutdown/exit close cleanly.
"""
from __future__ import annotations

from index_graph.lsp.server import LSPServer
from symbol_fixtures import simple_module


def test_initialize_advertises_definition_and_references(tmp_path):
    simple_module(tmp_path)
    server = LSPServer(root=tmp_path)
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"rootUri": None}})
    caps = resp["result"]["capabilities"]
    assert caps["definitionProvider"] is True
    assert caps["referencesProvider"] is True
    assert resp["result"]["serverInfo"]["name"]


def test_initialized_builds_graph(tmp_path):
    simple_module(tmp_path)
    server = LSPServer(root=tmp_path)
    server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert server.handle_request({"jsonrpc": "2.0", "method": "initialized",
                                  "params": {}}) is None
    assert server.symbol_graph is not None
    assert any(s.name == "foo" for s in server.symbol_graph.symbols)


def test_shutdown_then_exit(tmp_path):
    simple_module(tmp_path)
    server = LSPServer(root=tmp_path)
    server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    r = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "shutdown"})
    assert r["result"] is None
    assert server.handle_request({"jsonrpc": "2.0", "method": "exit"}) is None
    assert server.should_exit is True


def test_unknown_method_is_method_not_found(tmp_path):
    simple_module(tmp_path)
    server = LSPServer(root=tmp_path)
    r = server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "textDocument/bogus"})
    assert r["error"]["code"] == -32601
