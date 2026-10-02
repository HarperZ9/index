"""`index serve`: a stdlib http.server that serves the verified wiki on demand.

The URL-swap experience: GET /<forge-host>/<org>/<repo> reconstructs the git
URL https://<host>/<org>/<repo>, runs the EXISTING verified-wiki generation
(the same clone -> derive -> clean-up code path as `index wiki <url>`), and
serves the self-contained HTML. Consent-clean by construction: generation is
on demand only, nothing is crawled or pre-indexed, robots.txt disallows
indexing, and every page states that the wiki derives structure and defers to
the repo owner's authored docs. This is the LOCAL server component; deploying
or hosting it anywhere is a separate operator decision.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .cli import CloneError, clone_repo
from .html import render_wiki_html
from .pack import build_wiki_pack
from .serve_pages import ROBOTS_TXT, error_page, inject_banner, landing_page

# A route segment: a plain forge/org/repo token. No slashes, no traversal, no
# leading dot, no scheme or userinfo. Deliberately strict; anything else is 400.
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ALLOWED_HOSTS = None  # None = any host of the right shape; a set narrows it.


class RouteError(ValueError):
    """A request path is not a valid /<host>/<org>/<repo> route. The message is
    a plain reason, safe to show a user, with no traceback."""


def parse_route(path: str) -> tuple[str, str, str]:
    """Parse /<forge-host>/<org>/<repo> into (host, org, repo), or raise
    RouteError. Tolerates a trailing slash and a trailing `.git` on the repo."""
    trimmed = path.split("?", 1)[0].split("#", 1)[0].strip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[:-4]
    parts = trimmed.split("/")
    if len(parts) != 3:
        raise RouteError(
            "a repo route is host/org/repo (e.g. /github.com/org/repo); "
            "this path is not that shape")
    host, org, repo = parts
    for label, seg in (("host", host), ("org", org), ("repo", repo)):
        if not _SEGMENT.match(seg):
            raise RouteError(f"the {label} segment {seg!r} is not a plain "
                             "host/org/repo token")
    if "." not in host:
        raise RouteError(f"the host segment {host!r} is not a forge host")
    if _ALLOWED_HOSTS is not None and host not in _ALLOWED_HOSTS:
        raise RouteError(f"forge host {host!r} is not on the allow-list")
    return host, org, repo


def build_git_url(host: str, org: str, repo: str) -> str:
    """Reconstruct the https git URL from a parsed route. Always https, never a
    scp-style or ssh URL, so only http(s) forge URLs are ever cloned."""
    return f"https://{host}/{org}/{repo}"


def wiki_for_route(path: str) -> str:
    """Derive and render the verified wiki for a route, banner injected. Reuses
    the `index wiki <url>` path: shallow clone, derive, always clean up."""
    host, org, repo = parse_route(path)
    url = build_git_url(host, org, repo)
    dest = Path(tempfile.mkdtemp(prefix="index-serve-"))
    try:
        clone_repo(url, dest)
        pack = build_wiki_pack(dest, repo_name=repo)
        return inject_banner(render_wiki_html(pack))
    finally:
        shutil.rmtree(dest, ignore_errors=True)


class _WikiHandler(BaseHTTPRequestHandler):
    server_version = "index-serve"

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        route = self.path.split("?", 1)[0]
        if route == "/":
            return self._send(200, landing_page(), "text/html; charset=utf-8")
        if route == "/robots.txt":
            return self._send(200, ROBOTS_TXT.encode("utf-8"),
                              "text/plain; charset=utf-8")
        if route == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        self._serve_wiki(route)

    do_HEAD = do_GET

    def _serve_wiki(self, route: str) -> None:
        try:
            html = wiki_for_route(route)
        except RouteError as exc:
            return self._send(400, error_page(400, str(exc)),
                              "text/html; charset=utf-8")
        except CloneError as exc:
            reason = f"could not build the wiki: {exc}"
            return self._send(502, error_page(502, reason),
                              "text/html; charset=utf-8")
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def log_message(self, *args) -> None:  # keep the server quiet in tests
        return


def make_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    """Bind a threading HTTP server on (host, port). Default loopback; port 0
    picks an ephemeral port (used by the tests). The caller runs serve_forever."""
    return ThreadingHTTPServer((host, port), _WikiHandler)


def serve_forever(host: str = "127.0.0.1", port: int = 8000) -> int:
    """Bind and run the server until interrupted. Prints the bound address and
    the consent-clean posture, then blocks."""
    server = make_server(host, port)
    bound_host, bound_port = server.server_address
    print(f"index serve: http://{bound_host}:{bound_port}/ "
          "(on-demand verified wiki; robots.txt disallows indexing)")
    print("derive-not-generate, commit-pinned, re-checkable; "
          "defers to the repo owner's authored docs. Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nindex serve: stopped")
    finally:
        server.server_close()
    return 0
