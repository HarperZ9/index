"""The LSP server: dispatch, workspace state, and the two providers.

State is deliberately thin. On ``initialize``/``initialized`` the server builds
the wave-1 symbol graph for its single ``--root`` workspace and records a content
fingerprint of the Python tree. Before answering ``textDocument/definition`` or
``textDocument/references`` it re-checks that fingerprint: if the tree moved on
disk, it returns a typed STALE error instead of an answer derived from a graph
that no longer describes the files. Every positive answer is an evidence-backed
Location from the graph; an unresolved name is null (definition) or [] (references),
never a guess, and never a symbol from outside this root.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from ..graph.walk import walk_files
from ..symbols import build_symbol_graph
from ..symbols.model import SymbolGraph
from . import protocol
from .protocol import make_error, make_response
from .symbols_lsp import (find_symbol_at_position, path_to_uri, to_lsp_location,
                          to_lsp_range)

# JSON-RPC error codes.
METHOD_NOT_FOUND = -32601
STALE_CODE = -32603  # Internal Error: the workspace changed since initialize

_SERVER_NAME = "index-lsp"


def _fingerprint(root: Path) -> str:
    """A content fingerprint of the Python tree under root: SHA-256 over the
    sorted (relative-path, file-sha) pairs. A changed, added, or removed .py
    file moves the fingerprint; a stable tree keeps it byte-identical."""
    root = Path(root).resolve()
    entries: list[str] = []
    for py in walk_files(root, suffixes=(".py",)):
        try:
            rel = py.relative_to(root).as_posix()
        except ValueError:
            rel = py.as_posix()
        try:
            digest = hashlib.sha256(py.read_bytes()).hexdigest()
        except OSError:
            digest = "unreadable"
        entries.append(f"{rel}:{digest}")
    entries.sort()
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


class LSPServer:
    """A single-workspace language server over the wave-1 symbol graph."""

    def __init__(self, root: Path, trace: str = "off") -> None:
        self.root = Path(root).resolve()
        self.trace = trace
        self.symbol_graph: SymbolGraph | None = None
        self.fingerprint: str | None = None
        self.should_exit = False
        self._shutdown = False

    # --- lifecycle -----------------------------------------------------------

    def _build(self) -> None:
        """Build (or rebuild) the symbol graph and pin the current fingerprint."""
        self.symbol_graph = build_symbol_graph(self.root)
        self.fingerprint = _fingerprint(self.root)

    def is_stale(self) -> bool:
        """True when the Python tree changed on disk since the last build."""
        if self.fingerprint is None:
            return False
        return _fingerprint(self.root) != self.fingerprint

    # --- dispatch ------------------------------------------------------------

    def handle_request(self, req: dict) -> dict | None:
        method = req.get("method")
        rid = req.get("id")

        if method == "initialize":
            root = self._root_from_params(req.get("params") or {})
            if root is not None:
                self.root = root
            return make_response(rid, self._capabilities())
        if method == "initialized":
            self._build()
            return None
        if method == "shutdown":
            self._shutdown = True
            return make_response(rid, None)
        if method == "exit":
            self.should_exit = True
            return None
        if method == "textDocument/didOpen":
            return None  # tracked implicitly; staleness is fingerprint-based
        if method == "textDocument/definition":
            return self._guarded(rid, self._definition, req.get("params") or {})
        if method == "textDocument/references":
            return self._guarded(rid, self._references, req.get("params") or {})
        if rid is None:
            return None  # an unknown notification: nothing to answer
        return make_error(rid, METHOD_NOT_FOUND, f"method not found: {method}")

    def _root_from_params(self, params: dict) -> Path | None:
        """Honor an explicit rootUri/rootPath from the client, else keep --root."""
        uri = params.get("rootUri")
        if isinstance(uri, str) and uri:
            from .symbols_lsp import uri_to_path
            return uri_to_path(uri)
        path = params.get("rootPath")
        if isinstance(path, str) and path:
            return Path(path).resolve()
        return None

    def _capabilities(self) -> dict:
        from .. import __version__
        return {"capabilities": {"definitionProvider": True,
                                 "referencesProvider": True,
                                 "textDocumentSync": 1},
                "serverInfo": {"name": _SERVER_NAME, "version": __version__}}

    def _guarded(self, rid, handler, params: dict) -> dict:
        """Run a provider, but first fail closed if the workspace is stale."""
        if self.symbol_graph is None:
            self._build()
        if self.is_stale():
            return make_error(rid, STALE_CODE,
                              "workspace changed on disk since initialize; "
                              "re-initialize the LSP server (stale graph blocked)")
        return make_response(rid, handler(params))

    # --- providers -----------------------------------------------------------

    def _symbol_under_cursor(self, params: dict):
        uri = (params.get("textDocument") or {}).get("uri") or ""
        position = params.get("position") or {}
        return find_symbol_at_position(uri, position, self.symbol_graph, self.root)

    def _definition(self, params: dict):
        """Return an LSP Location for the symbol under the cursor, or null."""
        sym = self._symbol_under_cursor(params)
        if sym is None:
            return None  # unresolved / outside root / not an identifier: never a guess
        return to_lsp_location(sym, self.root)

    def _references(self, params: dict) -> list:
        """Return every resolved caller of the symbol under the cursor.

        Unresolved references are excluded: they are not evidence-backed edges.
        """
        sym = self._symbol_under_cursor(params)
        if sym is None:
            return []
        graph = self.symbol_graph
        assert graph is not None
        locations: list[dict] = []
        seen: set[tuple[str, int]] = set()
        for call in graph.calls:
            if call.to_symbol != sym.id:
                continue
            key = (call.evidence_file, call.evidence_line)
            if key in seen:
                continue
            seen.add(key)
            uri = path_to_uri(self.root / call.evidence_file)
            locations.append({"uri": uri, "range": to_lsp_range(call.evidence_line)})
        include_decl = ((params.get("context") or {}).get("includeDeclaration"))
        if include_decl:
            locations.insert(0, to_lsp_location(sym, self.root))
        return locations

    # --- main loop -----------------------------------------------------------

    def serve(self, stdin=None, stdout=None) -> int:
        """Read Content-Length-framed JSON-RPC from stdin, answer on stdout."""
        stdin = stdin if stdin is not None else sys.stdin.buffer
        stdout = stdout if stdout is not None else sys.stdout.buffer
        while not self.should_exit:
            msg = protocol.read_message(stdin)
            if msg is None:
                break
            resp = self.handle_request(msg)
            if resp is not None:
                protocol.write_message(stdout, resp)
        return 0


def serve(root: Path, trace: str = "off", stdin=None, stdout=None) -> int:
    """Start an LSPServer on root and run its stdio loop."""
    return LSPServer(root=root, trace=trace).serve(stdin, stdout)
