"""Static pages and the consent-clean banner for the on-demand wiki server.

Kept separate from serve.py so both stay under the file-size ceiling. Every
page states the same posture: the wiki DERIVES structure from the dependency
graph, generates no prose, is commit-pinned and re-checkable, and defers to
the repo owner's authored docs. Nothing here crawls, pre-indexes, or publishes.
"""
from __future__ import annotations

from html import escape

from ..viz.theme import css_variables

# One sentence reused verbatim on the landing page and injected into every
# served wiki, so the derive-not-generate posture is never missing.
DERIVE_BANNER = (
    "This wiki derives structure from the dependency graph and does not "
    "generate prose. It is commit-pinned and re-checkable with "
    "index wiki --verify, and it defers to the repo owner's authored docs."
)

_PAGE_CSS = (
    "body{margin:0;background:var(--bg);color:var(--ink);"
    "font-family:var(--font-body);line-height:1.5}"
    "main{max-width:44rem;margin:0 auto;padding:2rem 1.2rem}"
    "h1{font-family:var(--font-mono);font-size:1.4rem}"
    "code{font-family:var(--font-mono)}"
    ".note{border:1px solid var(--hairline);border-radius:6px;padding:.8rem 1rem;"
    "background:rgba(70,54,232,.05);font-size:.92rem}"
    "a{color:var(--accent)}"
    "footer{margin-top:2rem;font-family:var(--font-mono);font-size:.78rem;"
    "color:var(--muted)}"
)

# The consent-clean banner as an HTML fragment, injected into served wikis.
BANNER_HTML = (
    '<div style="font-family:var(--font-mono,monospace);font-size:.8rem;'
    "padding:.5rem 1rem;background:rgba(70,54,232,.08);"
    'border-bottom:1px solid rgba(11,12,14,.14)">'
    f"{escape(DERIVE_BANNER)}</div>"
)

ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


def _shell(title: str, body: str) -> bytes:
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title>"
        f"<style>{css_variables()}{_PAGE_CSS}</style></head><body>"
        f"<main>{body}</main></body></html>"
    ).encode("utf-8")


def landing_page() -> bytes:
    """The root page: how to use the server, stated in consent-clean terms."""
    body = (
        "<h1>index serve</h1>"
        "<p>A local server that derives a verified wiki for one repository "
        "<strong>on demand</strong>. Request a repo by its forge path and index "
        "shallow-clones it, derives the wiki from its dependency graph, serves "
        "the self-contained page, and removes the clone.</p>"
        "<p>Try a path of the shape "
        "<code>/&lt;forge-host&gt;/&lt;org&gt;/&lt;repo&gt;</code>, for example "
        "<code>/github.com/org/repo</code>.</p>"
        f'<p class="note">{escape(DERIVE_BANNER)}</p>'
        "<p>Generation is on demand only: nothing is crawled or pre-indexed, and "
        "this local server publishes nothing. Deploying or hosting it anywhere is "
        "a separate operator decision.</p>"
        "<footer>index wiki, derived from the module graph, never generated "
        "prose. robots.txt disallows indexing.</footer>"
    )
    return _shell("index serve", body)


def error_page(status: int, reason: str) -> bytes:
    """A plain error page, never a stack trace."""
    body = (
        f"<h1>{status}</h1>"
        f"<p>{escape(reason)}</p>"
        '<p><a href="/">back to the landing page</a></p>'
    )
    return _shell(f"index serve: {status}", body)


def inject_banner(wiki_html: str) -> str:
    """Insert the consent-clean banner just inside the served wiki's <body>."""
    marker = "<body>"
    idx = wiki_html.find(marker)
    if idx < 0:
        return BANNER_HTML + wiki_html
    cut = idx + len(marker)
    return wiki_html[:cut] + BANNER_HTML + wiki_html[cut:]
