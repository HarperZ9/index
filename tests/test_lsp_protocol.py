"""Content-Length framing and JSON-RPC 2.0 helpers for the LSP stdio protocol.

The LSP transport is not newline-delimited like the MCP face: it frames each
message with a ``Content-Length`` header (RFC 3156-style), then the JSON body.
These tests pin the byte-level framing so an IDE client and the server agree.
"""
from __future__ import annotations

import io

from index_graph.lsp.protocol import (make_error, make_response, read_message,
                                       write_message)


def _frame(body: str) -> bytes:
    return f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n{body}".encode("utf-8")


def test_read_message_parses_content_length_frame():
    body = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
    stream = io.BytesIO(_frame(body))
    msg = read_message(stream)
    assert msg["id"] == 1
    assert msg["method"] == "initialize"


def test_read_message_returns_none_at_eof():
    assert read_message(io.BytesIO(b"")) is None


def test_read_message_handles_multiple_frames_in_sequence():
    a = '{"jsonrpc":"2.0","id":1,"method":"a"}'
    b = '{"jsonrpc":"2.0","id":2,"method":"b"}'
    stream = io.BytesIO(_frame(a) + _frame(b))
    assert read_message(stream)["method"] == "a"
    assert read_message(stream)["method"] == "b"
    assert read_message(stream) is None


def test_read_message_ignores_extra_headers():
    body = '{"jsonrpc":"2.0","id":7,"method":"ping"}'
    raw = (f"Content-Length: {len(body)}\r\n"
           f"Content-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n"
           f"{body}").encode("utf-8")
    msg = read_message(io.BytesIO(raw))
    assert msg["id"] == 7


def test_write_message_emits_content_length_header():
    out = io.BytesIO()
    write_message(out, {"jsonrpc": "2.0", "id": 1, "result": {}})
    raw = out.getvalue()
    assert raw.startswith(b"Content-Length: ")
    assert b"\r\n\r\n" in raw
    header, _, body = raw.partition(b"\r\n\r\n")
    declared = int(header.split(b"Content-Length:")[1].strip())
    assert declared == len(body)


def test_write_then_read_roundtrip():
    out = io.BytesIO()
    write_message(out, {"jsonrpc": "2.0", "id": 5, "result": {"ok": True}})
    back = read_message(io.BytesIO(out.getvalue()))
    assert back["id"] == 5
    assert back["result"]["ok"] is True


def test_make_response_shape():
    r = make_response(3, {"value": 1})
    assert r == {"jsonrpc": "2.0", "id": 3, "result": {"value": 1}}


def test_make_error_shape():
    r = make_error(9, -32603, "workspace changed")
    assert r["jsonrpc"] == "2.0"
    assert r["id"] == 9
    assert r["error"]["code"] == -32603
    assert r["error"]["message"] == "workspace changed"
