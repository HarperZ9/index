"""LSP stdio framing and JSON-RPC 2.0 helpers, hand-rolled, zero dependencies.

Unlike the newline-delimited MCP face, the Language Server Protocol frames each
message with a ``Content-Length`` header followed by a blank line and then the
UTF-8 JSON body (RFC 3156-style). These helpers read and write that framing over
binary streams and build the JSON-RPC response/error envelopes, nothing more:
dispatch and state live in ``server.py``.
"""
from __future__ import annotations

import json
from typing import BinaryIO

_HEADER_SEP = b"\r\n"
_HEADER_END = b"\r\n\r\n"


def read_message(stream: BinaryIO) -> dict | None:
    """Read one Content-Length-framed JSON message, or None at end of stream.

    Reads header lines until the blank separator, honors the ``Content-Length``
    header (ignoring any others such as ``Content-Type``), then reads exactly
    that many body bytes and parses them as JSON. A truncated frame or a body
    that is not a JSON object reads as None (end of usable input).
    """
    length: int | None = None
    while True:
        line = _read_header_line(stream)
        if line is None:
            return None  # EOF before a complete header block
        if line == b"":
            break  # blank line: header block ends
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            try:
                length = int(value.strip())
            except ValueError:
                return None
    if length is None:
        return None
    body = _read_exact(stream, length)
    if body is None:
        return None
    try:
        msg = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return msg if isinstance(msg, dict) else None


def _read_header_line(stream: BinaryIO) -> bytes | None:
    """Read one CRLF-terminated header line (without the CRLF); None at EOF."""
    buf = bytearray()
    while True:
        ch = stream.read(1)
        if not ch:
            return None if not buf else bytes(buf)
        buf += ch
        if buf.endswith(_HEADER_SEP):
            return bytes(buf[:-2])


def _read_exact(stream: BinaryIO, n: int) -> bytes | None:
    """Read exactly n bytes; None if the stream ends early."""
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def write_message(stream: BinaryIO, message: dict) -> None:
    """Frame a JSON-RPC message with a Content-Length header and flush it."""
    body = json.dumps(message).encode("utf-8")
    stream.write(b"Content-Length: " + str(len(body)).encode("ascii") + _HEADER_END)
    stream.write(body)
    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def make_response(rid, result) -> dict:
    """A JSON-RPC 2.0 success response."""
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def make_error(rid, code: int, message: str) -> dict:
    """A JSON-RPC 2.0 error response."""
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}
