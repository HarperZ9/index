"""Handler for `index lsp`: start the stdio LSP server on a workspace root.

A thin adapter over ``index_graph.lsp.LSPServer``. It binds no socket and holds
no model; it reads Content-Length-framed JSON-RPC from stdin and writes answers
to stdout, so an IDE (VSCode/Neovim/JetBrains) can consume index's verified
symbol graph natively. Tests may inject in-memory binary streams via the private
``_stdin``/``_stdout`` attributes on the args object.
"""
from __future__ import annotations


def cmd_lsp(args) -> int:
    from ..lsp import LSPServer

    server = LSPServer(root=args.root, trace=getattr(args, "trace", "off"))
    return server.serve(getattr(args, "_stdin", None), getattr(args, "_stdout", None))
