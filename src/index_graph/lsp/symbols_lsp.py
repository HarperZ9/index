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

from ..symbols.model import SymbolDefinition, SymbolGraph

# Identifier characters for the "word under the cursor" scan.
_IDENT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def path_to_uri(path: Path) -> str:
    """A file:// URI for a filesystem path (resolved, percent-encoded).

    Uses ``Path.as_uri`` so the result is a well-formed ``file://`` URI on both
    POSIX (``file:///tmp/x``) and Windows (``file:///C:/x``); hand-building it
    from ``pathname2url`` yielded a single-slash ``file:/tmp/x`` on POSIX.
    """
    return Path(path).resolve().as_uri()


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
    workspace resolves to None (never a cross-repo guess). Resolution defers
    entirely to the wave-1 graph's own verdict, so nothing is guessed:

      - A cursor on a definition line resolves to that definition.
      - A cursor on a call site resolves via the ``SymbolCall`` recorded at that
        exact (file, line): a resolved call (``to_symbol`` set) jumps to its
        target definition; an unresolved call (``to_symbol`` None, e.g. a
        same-named symbol elsewhere with no import/call edge) resolves to None,
        never to a bare-name match against an unrelated definition.
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
    line_1 = line_no + 1
    # Cursor on a definition line in this file: return that definition.
    on_line = [s for s in graph.symbols
               if s.file == rel and s.name == word and s.line == line_1]
    if on_line:
        return on_line[0]
    # Cursor on a call site: defer to the graph's resolution for THIS exact call
    # site. A resolved call names its target; an unresolved call names None.
    by_id = {s.id: s for s in graph.symbols}
    for call in graph.calls:
        if (call.evidence_file == rel and call.evidence_line == line_1
                and call.to_name == word):
            if call.to_symbol is not None:
                return by_id.get(call.to_symbol)
            return None  # graph classified this call unresolved: never guess
    return None
