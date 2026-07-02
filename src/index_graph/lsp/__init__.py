"""LSP server: IDE-facing go-to-definition and find-references over the wave-1
symbol graph, hand-rolled Content-Length framing, zero runtime dependencies.

``index lsp --root ROOT`` starts a stdio JSON-RPC 2.0 language server that
answers ``textDocument/definition`` and ``textDocument/references`` from the
existing symbol-level call/reference graph. Every answer is evidence-backed
(a resolved file:line) or honestly empty; an unresolved reference is never
guessed into a jump, and a workspace that changed on disk is detected, not
silently answered from a stale graph.
"""
from __future__ import annotations

from .server import LSPServer, serve

__all__ = ["LSPServer", "serve"]
