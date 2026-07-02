"""`index serve`: an on-demand, consent-clean, local verified-wiki server.

The server never crawls and never pre-indexes: a wiki is derived only when a
route is requested, exactly through the `index wiki <url>` code path (shallow
clone, derive, clean up). These tests bind an ephemeral loopback port for the
one integration case and monkeypatch the clone step to a LOCAL repo, so no
network is touched.
"""
from __future__ import annotations

import http.client
import json
import threading

import pytest

from index_graph.wiki import serve as serve_mod
from index_graph.wiki.serve import (
    RouteError,
    build_git_url,
    make_server,
    parse_route,
)

from wiki_fixtures import git_commit_all, make_repo

DERIVE_BANNER = "derives structure from the dependency graph"


# --- route parsing (no socket) ------------------------------------------------


def test_parse_route_extracts_host_org_repo():
    host, org, repo = parse_route("/github.com/acme/widget")
    assert (host, org, repo) == ("github.com", "acme", "widget")


def test_parse_route_reconstructs_https_git_url():
    assert build_git_url(*parse_route("/github.com/acme/widget")) == (
        "https://github.com/acme/widget"
    )


def test_parse_route_tolerates_trailing_slash_and_dot_git():
    assert parse_route("/gitlab.com/acme/widget.git/") == (
        "gitlab.com",
        "acme",
        "widget",
    )


@pytest.mark.parametrize(
    "bad",
    [
        "/",  # root, not a repo route
        "/github.com",  # missing org + repo
        "/github.com/acme",  # missing repo
        "/github.com/acme/widget/extra",  # too deep
        "/../etc/passwd",  # traversal-shaped
        "/git@github.com/acme/widget",  # scp-style, not host/org/repo
        "/github.com/acme/.hidden",  # dot-leading segment
    ],
)
def test_parse_route_rejects_malformed(bad):
    with pytest.raises(RouteError):
        parse_route(bad)


# --- handler behavior via the test client (no clone) --------------------------


def _client(server):
    host, port = server.server_address
    return http.client.HTTPConnection(host, port, timeout=5)


def _get(server, path):
    conn = _client(server)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8"), resp.getheader("Content-Type")
    finally:
        conn.close()


@pytest.fixture
def server():
    srv = make_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def test_root_serves_landing_page_with_consent_posture(server):
    status, body, ctype = _get(server, "/")
    assert status == 200
    assert "text/html" in ctype
    assert DERIVE_BANNER in body
    assert "defers to" in body.lower()
    # the landing page must not claim it hosts or publishes anything
    assert "on demand" in body.lower()


def test_robots_txt_disallows_indexing(server):
    status, body, ctype = _get(server, "/robots.txt")
    assert status == 200
    assert "text/plain" in ctype
    assert "User-agent: *" in body
    assert "Disallow: /" in body


def test_malformed_route_returns_typed_400_without_traceback(server):
    status, body, _ = _get(server, "/github.com/acme")
    assert status == 400
    assert "Traceback" not in body
    assert "not the shape" in body.lower() or "host/org/repo" in body.lower()


def test_clone_failure_returns_plain_502_not_a_traceback(server, monkeypatch):
    def _boom(url, dest):
        raise serve_mod.CloneError(f"could not clone {url}: simulated failure")

    monkeypatch.setattr(serve_mod, "clone_repo", _boom)
    status, body, _ = _get(server, "/github.com/acme/widget")
    assert status == 502
    assert "Traceback" not in body
    assert "could not build the wiki" in body.lower()


def test_route_serves_the_verified_wiki_from_a_local_repo(server, monkeypatch, tmp_path):
    repo = make_repo(tmp_path / "widget")
    git_commit_all(repo)

    def _local_clone(url, dest):
        # Offline stand-in for the network clone: copy the local seed repo in.
        import shutil

        shutil.copytree(repo, dest, dirs_exist_ok=True)

    monkeypatch.setattr(serve_mod, "clone_repo", _local_clone)
    status, body, ctype = _get(server, "/github.com/acme/widget")
    assert status == 200
    assert "text/html" in ctype
    # the real verified-wiki content is present ...
    assert "index wiki:" in body
    assert "pinned to" in body
    # ... and the consent-clean derive-not-generate banner is injected
    assert DERIVE_BANNER in body


def test_favicon_request_is_handled_quietly(server):
    status, _, _ = _get(server, "/favicon.ico")
    assert status in (204, 404)


# --- CLI + status wiring (AGENTS.md alignment) --------------------------------


def test_serve_subcommand_dispatches_to_the_server(monkeypatch):
    from index_graph.cli import main

    captured = {}

    def _fake_serve_forever(host="127.0.0.1", port=8000):
        captured["host"], captured["port"] = host, port
        return 0

    monkeypatch.setattr(
        "index_graph.wiki.serve.serve_forever", _fake_serve_forever
    )
    assert main(["serve", "--host", "127.0.0.1", "--port", "0"]) == 0
    assert captured == {"host": "127.0.0.1", "port": 0}


def test_serve_default_binds_loopback(monkeypatch):
    from index_graph.cli import main

    captured = {}
    monkeypatch.setattr(
        "index_graph.wiki.serve.serve_forever",
        lambda host="127.0.0.1", port=8000: captured.update(host=host, port=port) or 0,
    )
    assert main(["serve"]) == 0
    assert captured["host"] == "127.0.0.1"


def test_status_advertises_the_serve_surface(capsys):
    from index_graph.cli import main

    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "serve" in payload["native"]["commands"]
