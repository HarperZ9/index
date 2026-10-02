"""Zero-dependency GFM-lite markdown -> escaping-safe HTML for atlas docs."""
from __future__ import annotations

import re
from html import escape as _esc          # &<>"' -> entities (quote=True by default)

from .docs import _norm                  # shared normalizer: space/underscore -> dash, lower

_CODE = re.compile(r"`([^`]+)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_WIKILINK = re.compile(r"\[\[\s*([^\]|]+?)\s*(?:\|\s*([^\]]*?)\s*)?\]\]")
_LINK = re.compile(r"\[([^\]]+)\]\(\s*([^()]*(?:\([^)]*\))*[^()]*?)\s*\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
# permitted href schemes: http(s), mailto, anchors, relative paths. NOT javascript:/data:/vbscript:.
_SAFE_URL = re.compile(r"^(?:https?:|mailto:|#|/|\./|\.\./|[^:]*$)", re.I)


def _wiki_sub(m: "re.Match") -> str:
    target, alias = m.group(1), m.group(2)
    label = alias if alias else target            # already inside escaped text
    return ('<a class="wikilink" href="#" data-atlas-target="%s">%s</a>'
            % (_esc(_norm(target), quote=True), label))


def _link_sub(m: "re.Match") -> str:
    label, url = m.group(1), m.group(2)
    if not _SAFE_URL.match(url):
        return label                              # drop unsafe scheme, keep the text
    return '<a href="%s" rel="noopener noreferrer">%s</a>' % (url, label)


def render_inline(text: str) -> str:
    text = text.replace("\x00", "")   # strip NUL so a doc body can't forge a code-span sentinel
    codes: list[str] = []

    def _stash(m: "re.Match") -> str:
        codes.append("<code>" + _esc(m.group(1)) + "</code>")
        return "\x00%d\x00" % (len(codes) - 1)    # null-byte sentinel: absent from markdown, survives escaping

    text = _CODE.sub(_stash, text)
    text = _esc(text)                             # escape all remaining literal text
    text = _IMAGE.sub(lambda m: '<span class="md-img">' + m.group(1) + "</span>", text)
    text = _WIKILINK.sub(_wiki_sub, text)
    text = _LINK.sub(_link_sub, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)
    return text


_HEADING = re.compile(r"(#{1,6})\s+(.*)$")
_ULI = re.compile(r"\s*[-*+]\s+(.*)$")
_OLI = re.compile(r"\s*\d+[.)]\s+(.*)$")
_TASK = re.compile(r"\s*[-*+]\s+\[([ xX])\]\s+(.*)$")
_BQ = re.compile(r">\s?(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")


def _starts_block(line: str) -> bool:
    return bool(_HEADING.match(line) or _ULI.match(line) or _OLI.match(line)
                or line.startswith("```") or line.startswith(">") or "|" in line)


def _render_li(text: str) -> str:
    task = _TASK.match(text)
    if task:
        checked = " checked" if task.group(1) in ("x", "X") else ""
        return ('<li class="task"><input type="checkbox"%s disabled> %s</li>'
                % (checked, render_inline(task.group(2).strip())))
    body = (_ULI.match(text) or _OLI.match(text)).group(1)
    return "<li>" + render_inline(body.strip()) + "</li>"


def _consume_list(lines: list[str], i: int) -> tuple[str, int]:
    ordered = bool(_OLI.match(lines[i]) and not _ULI.match(lines[i]))
    items: list[str] = []
    while i < len(lines) and (_ULI.match(lines[i]) or _OLI.match(lines[i])):
        items.append(_render_li(lines[i]))
        i += 1
    tag = "ol" if ordered else "ul"
    return "<%s>\n%s\n</%s>" % (tag, "\n".join(items), tag), i


def _is_table(lines: list[str], i: int) -> bool:
    return ("|" in lines[i] and i + 1 < len(lines) and bool(_TABLE_SEP.match(lines[i + 1])))


def _row_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _consume_table(lines: list[str], i: int) -> tuple[str, int]:
    head = _row_cells(lines[i]); i += 2          # header row + separator row
    body: list[str] = []
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        cells = _row_cells(lines[i])
        body.append("<tr>" + "".join("<td>" + render_inline(c) + "</td>" for c in cells) + "</tr>")
        i += 1
    thead = "<tr>" + "".join("<th>" + render_inline(c) + "</th>" for c in head) + "</tr>"
    return "<table>\n<thead>%s</thead>\n<tbody>%s</tbody>\n</table>" % (thead, "\n".join(body)), i


def render_markdown(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("```"):
            i += 1
            buf: list[str] = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1                                    # skip the closing fence (or run off end)
            out.append("<pre><code>" + _esc("\n".join(buf)) + "</code></pre>")
            continue
        h = _HEADING.match(line)
        if h:
            lvl = len(h.group(1))
            out.append("<h%d>%s</h%d>" % (lvl, render_inline(h.group(2).strip()), lvl))
            i += 1; continue
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(_BQ.match(lines[i]).group(1)); i += 1
            out.append("<blockquote>" + render_inline(" ".join(b for b in buf if b)) + "</blockquote>")
            continue
        if _is_table(lines, i):
            block, i = _consume_table(lines, i)
            out.append(block); continue
        if _ULI.match(line) or _OLI.match(line):
            block, i = _consume_list(lines, i)
            out.append(block); continue
        if line.strip() == "":
            i += 1; continue
        # Always consume the line that opened the paragraph. It may LOOK like a
        # block starter (a prose line containing "|" that is not a table), but
        # every real block was dispatched above; skipping it here would loop
        # forever on the same line.
        buf = [line]
        i += 1
        while i < n and lines[i].strip() != "" and not _starts_block(lines[i]):
            buf.append(lines[i]); i += 1
        out.append("<p>" + render_inline(" ".join(buf)) + "</p>")
    return "\n".join(out)
