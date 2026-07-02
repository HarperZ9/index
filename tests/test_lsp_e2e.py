"""End-to-end IDE simulation over the LSP server: a full session that drives
initialize -> initialized -> definition/references -> shutdown -> exit, plus the
three can-it-FAIL negatives on one server object (cross-repo isolation,
unresolved-null, staleness).
"""
from __future__ import annotations

import io
import json

from index_graph.lsp import protocol, serve
from index_graph.lsp.server import STALE_CODE
from index_graph.lsp.symbols_lsp import path_to_uri
from symbol_fixtures import cross_module


def _frame(msg: dict) -> bytes:
    body = json.dumps(msg).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


def _drain(raw: bytes) -> dict:
    stream = io.BytesIO(raw)
    by_id: dict = {}
    while True:
        m = protocol.read_message(stream)
        if m is None:
            break
        if "id" in m:
            by_id[m["id"]] = m
    return by_id


def test_full_session_definition_and_references(tmp_path):
    cross_module(tmp_path)  # app.main() calls exported() from lib
    app_uri = path_to_uri(tmp_path / "app.py")
    lib_uri = path_to_uri(tmp_path / "lib.py")
    stdin = io.BytesIO(
        _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + _frame({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        # go-to-definition on the exported() call in app.py -> lib.py
        + _frame({"jsonrpc": "2.0", "id": 2, "method": "textDocument/definition",
                  "params": {"textDocument": {"uri": app_uri},
                             "position": {"line": 4, "character": 4}}})
        # find-references on exported() def in lib.py -> the app.py call site
        + _frame({"jsonrpc": "2.0", "id": 3, "method": "textDocument/references",
                  "params": {"textDocument": {"uri": lib_uri},
                             "position": {"line": 0, "character": 4},
                             "context": {"includeDeclaration": False}}})
        + _frame({"jsonrpc": "2.0", "id": 4, "method": "shutdown"})
        + _frame({"jsonrpc": "2.0", "method": "exit"}))
    stdout = io.BytesIO()
    rc = serve(tmp_path, stdin=stdin, stdout=stdout)
    assert rc == 0
    by_id = _drain(stdout.getvalue())
    assert by_id[2]["result"]["uri"] == lib_uri  # resolved cross-module jump
    refs = by_id[3]["result"]
    assert len(refs) == 1 and refs[0]["uri"] == app_uri
    assert by_id[4]["result"] is None


def test_e2e_cross_repo_isolation_negative(tmp_path):
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "a.py").write_text("def run():\n    only_b()\n", encoding="utf-8")
    (repo_b / "b.py").write_text("def only_b():\n    pass\n", encoding="utf-8")
    a_uri = path_to_uri(repo_a / "a.py")
    stdin = io.BytesIO(
        _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + _frame({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        + _frame({"jsonrpc": "2.0", "id": 2, "method": "textDocument/definition",
                  "params": {"textDocument": {"uri": a_uri},
                             "position": {"line": 1, "character": 4}}})
        + _frame({"jsonrpc": "2.0", "method": "exit"}))
    stdout = io.BytesIO()
    serve(repo_a, stdin=stdin, stdout=stdout)  # server rooted at repo_a only
    by_id = _drain(stdout.getvalue())
    assert by_id[2]["result"] is None  # never jumps into repo_b


def test_e2e_unresolved_null_negative(tmp_path):
    (tmp_path / "m.py").write_text("def run():\n    ghost()\n", encoding="utf-8")
    uri = path_to_uri(tmp_path / "m.py")
    stdin = io.BytesIO(
        _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + _frame({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        + _frame({"jsonrpc": "2.0", "id": 2, "method": "textDocument/definition",
                  "params": {"textDocument": {"uri": uri},
                             "position": {"line": 1, "character": 4}}})
        + _frame({"jsonrpc": "2.0", "method": "exit"}))
    stdout = io.BytesIO()
    serve(tmp_path, stdin=stdin, stdout=stdout)
    by_id = _drain(stdout.getvalue())
    assert by_id[2]["result"] is None
    assert "error" not in by_id[2]


def test_e2e_staleness_negative(tmp_path):
    # initialize, then mutate on disk between initialized and the request
    from index_graph.lsp.server import LSPServer
    (tmp_path / "m.py").write_text("def foo():\n    pass\ndef bar():\n    foo()\n",
                                   encoding="utf-8")
    server = LSPServer(root=tmp_path)
    server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    server.handle_request({"jsonrpc": "2.0", "method": "initialized", "params": {}})
    (tmp_path / "m.py").write_text("def foo():\n    pass\ndef bar():\n    other()\n",
                                   encoding="utf-8")
    uri = path_to_uri(tmp_path / "m.py")
    r = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "textDocument/definition",
                               "params": {"textDocument": {"uri": uri},
                                          "position": {"line": 3, "character": 4}}})
    assert r["error"]["code"] == STALE_CODE
