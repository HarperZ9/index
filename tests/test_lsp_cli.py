"""`index lsp --root ROOT`: the subcommand parses, and cmd_lsp drives a full
Content-Length-framed session over in-memory binary streams.
"""
from __future__ import annotations

import io
import json

from index_graph.cli_handlers import cmd_lsp
from index_graph.cli_parser import build_parser
from index_graph.lsp.symbols_lsp import path_to_uri
from symbol_fixtures import simple_module


def _frame(msg: dict) -> bytes:
    body = json.dumps(msg).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


def _read_all(raw: bytes) -> list[dict]:
    from index_graph.lsp import protocol
    stream = io.BytesIO(raw)
    out = []
    while True:
        m = protocol.read_message(stream)
        if m is None:
            break
        out.append(m)
    return out


def test_lsp_subcommand_parses(tmp_path):
    args = build_parser().parse_args(["lsp", "--root", str(tmp_path)])
    assert args.cmd == "lsp"
    assert args.root == tmp_path


def test_cmd_lsp_runs_a_session(tmp_path):
    simple_module(tmp_path)
    uri = path_to_uri(tmp_path / "mod.py")
    stdin = io.BytesIO(
        _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + _frame({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        + _frame({"jsonrpc": "2.0", "id": 2, "method": "textDocument/definition",
                  "params": {"textDocument": {"uri": uri},
                             "position": {"line": 5, "character": 4}}})
        + _frame({"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
        + _frame({"jsonrpc": "2.0", "method": "exit"}))
    stdout = io.BytesIO()

    class Args:
        root = tmp_path
        trace = "off"

    args = Args()
    args._stdin = stdin
    args._stdout = stdout
    rc = cmd_lsp(args)
    assert rc == 0
    responses = _read_all(stdout.getvalue())
    by_id = {r.get("id"): r for r in responses if "id" in r}
    assert by_id[1]["result"]["capabilities"]["definitionProvider"] is True
    assert by_id[2]["result"]["uri"] == uri
    assert by_id[2]["result"]["range"]["start"]["line"] == 0
    assert by_id[3]["result"] is None
