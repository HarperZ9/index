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
