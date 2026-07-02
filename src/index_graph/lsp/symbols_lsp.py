"""Bridge the wave-1 symbol model to LSP positions and Locations.

Two conversions and one lookup, all deterministic and evidence-backed:
  - ``path_to_uri`` / ``uri_to_path``: file:// URIs the IDE speaks.
  - ``to_lsp_location``: a SymbolDefinition -> an LSP Location (0-indexed line,
    column 0; the client highlights the symbol name).
  - ``find_symbol_at_position``: given a document and a cursor, name the symbol
    the cursor sits on. A cursor on a definition line resolves to that symbol;
    a cursor on a call resolves to the identifier written under it, matched
    against real definitions (never guessed). A file outside the server root,
    or a cursor on whitespace/comment, resolves to None.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import pathname2url

from ..symbols.model import SymbolDefinition, SymbolGraph

# Identifier characters for the "word under the cursor" scan.
_IDENT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def path_to_uri(path: Path) -> str:
    """A file:// URI for a filesystem path (resolved, percent-encoded)."""
    return "file:" + pathname2url(str(Path(path).resolve()))


def uri_to_path(uri: str) -> Path:
    """The filesystem path a file:// URI names, resolved."""
    parsed = urlparse(uri)
    raw = unquote(parsed.path)
    # On Windows, urlparse leaves a leading slash before the drive letter.
    if len(raw) >= 3 and raw[0] == "/" and raw[2] == ":":
        raw = raw[1:]
    return Path(raw).resolve()


def to_lsp_range(line_1indexed: int) -> dict:
    """A zero-width LSP range at the start of a 1-indexed source line."""
    line0 = max(line_1indexed - 1, 0)
    return {"start": {"line": line0, "character": 0},
            "end": {"line": line0, "character": 0}}


def to_lsp_location(sym: SymbolDefinition, root: Path) -> dict:
    """An LSP Location for a SymbolDefinition, rooted at the workspace root."""
    uri = path_to_uri(Path(root) / sym.file)
    return {"uri": uri, "range": to_lsp_range(sym.line)}


def _word_at(line: str, character: int) -> str | None:
    """The identifier the cursor sits within, or None on non-identifier text."""
    if character < 0 or character > len(line):
        return None
    # A cursor exactly at end-of-word (character == len(word)) still counts.
    if character == len(line) or line[character] not in _IDENT:
        if character == 0 or line[character - 1] not in _IDENT:
            return None
    start = character
    while start > 0 and line[start - 1] in _IDENT:
        start -= 1
    end = character
    while end < len(line) and line[end] in _IDENT:
        end += 1
    word = line[start:end]
    return word or None


def find_symbol_at_position(
    uri: str, position: dict, graph: SymbolGraph, root: Path,
) -> SymbolDefinition | None:
    """Resolve the symbol under an LSP cursor against the wave-1 graph.

    Only files inside ``root`` are considered; a file outside the server's
    workspace resolves to None (never a cross-repo guess). The word under the
    cursor is matched against symbol definitions by bare name.
    """
    root = Path(root).resolve()
    path = uri_to_path(uri)
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return None  # document is outside this server's workspace root
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    lines = text.splitlines()
    line_no = position.get("line", 0)
    if line_no < 0 or line_no >= len(lines):
        return None
    word = _word_at(lines[line_no], position.get("character", 0))
    if not word:
        return None
    # Prefer a definition that lives on this exact line and file (cursor on a
    # def), else any definition of that bare name in this file, else any in the
    # graph. All are real definitions; nothing is guessed.
    in_file = [s for s in graph.symbols if s.file == rel and s.name == word]
    on_line = [s for s in in_file if s.line == line_no + 1]
    if on_line:
        return on_line[0]
    if in_file:
        return in_file[0]
    anywhere = [s for s in graph.symbols if s.name == word]
    return anywhere[0] if anywhere else None
