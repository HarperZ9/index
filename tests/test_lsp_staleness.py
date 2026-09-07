"""Staleness: a workspace that changed on disk after initialize is detected,
not silently answered from a stale graph. This is can-it-FAIL negative #3.
"""
from __future__ import annotations

import os

from index_graph.lsp.server import LSPServer, STALE_CODE
from index_graph.lsp.symbols_lsp import path_to_uri
from symbol_fixtures import write


def _init(server):
    server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    server.handle_request({"jsonrpc": "2.0", "method": "initialized", "params": {}})


def _rewrite_same_size_with_restored_mtime(root, rel, before, after):
    assert len(before.encode("utf-8")) == len(after.encode("utf-8"))
    path = root / rel
    stat = path.stat()
    write(root, rel, after)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    after_stat = path.stat()
    assert after_stat.st_size == stat.st_size
    assert after_stat.st_mtime_ns == stat.st_mtime_ns


def test_fingerprint_stable_when_nothing_changes(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    assert server.is_stale() is False
    assert server.is_stale() is False  # idempotent


def test_unchanged_tree_does_not_full_reread_per_request(tmp_path, monkeypatch):
    # Perf guard: on an unchanged tree, the cheap stat-only pre-check must take
    # the fast path so the expensive full-content fingerprint is NOT recomputed
    # on every definition/references request (IDEs issue these constantly).
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)  # the single build computes the full fingerprint exactly once
    import index_graph.lsp.server as srv
    safe_now = (tmp_path / "mod.py").stat().st_mtime_ns + srv._MTIME_UNCERTAINTY_NS + 1
    checked_at = server.last_content_check_mono_ns
    monkeypatch.setattr(srv, "_wall_time_ns", lambda: safe_now)
    monkeypatch.setattr(srv, "_monotonic_ns", lambda: checked_at + 1)
    real = srv._fingerprint
    calls = {"n": 0}

    def counting(root):
        calls["n"] += 1
        return real(root)

    monkeypatch.setattr(srv, "_fingerprint", counting)
    for _ in range(25):
        assert server.is_stale() is False
    assert calls["n"] == 0, (
        f"the full-content fingerprint was recomputed {calls['n']} times on an "
        "unchanged tree; the cheap pre-check should take the fast path")


def test_definition_on_stale_workspace_errors(tmp_path):
    before = "def foo():\n    pass\ndef bar():\n    foo()\n"
    after = "def foo():\n    pass\ndef bar():\n    baz()\n"
    write(tmp_path, "mod.py", before)
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "mod.py")
    # User edits the file on disk, outside the LSP protocol. The edit keeps the
    # byte size and restores the original mtime, matching the fast-path miss
    # seen when a same-size write lands inside the filesystem timestamp window.
    _rewrite_same_size_with_restored_mtime(tmp_path, "mod.py", before, after)
    r = server.handle_request({
        "jsonrpc": "2.0", "id": 10, "method": "textDocument/definition",
        "params": {"textDocument": {"uri": uri}, "position": {"line": 3, "character": 4}}})
    assert "error" in r
    assert r["error"]["code"] == STALE_CODE
    assert "stale" in r["error"]["message"].lower() or "chang" in r["error"]["message"].lower()


def test_same_size_restored_mtime_edit_is_stale(tmp_path):
    before = "def foo():\n    pass\ndef bar():\n    foo()\n"
    after = "def foo():\n    pass\ndef bar():\n    baz()\n"
    write(tmp_path, "mod.py", before)
    server = LSPServer(root=tmp_path)
    _init(server)
    _rewrite_same_size_with_restored_mtime(tmp_path, "mod.py", before, after)
    assert server.is_stale() is True


def test_same_size_old_mtime_edit_is_stale_after_recheck_bound(tmp_path, monkeypatch):
    import index_graph.lsp.server as srv

    before = "def foo():\n    pass\ndef bar():\n    foo()\n"
    after = "def foo():\n    pass\ndef bar():\n    baz()\n"
    write(tmp_path, "mod.py", before)
    old_mtime = 1_700_000_000_000_000_000
    os.utime(tmp_path / "mod.py", ns=(old_mtime, old_mtime))
    wall_now = old_mtime + srv._MTIME_UNCERTAINTY_NS + 1
    mono_now = {"value": 100_000_000_000}
    monkeypatch.setattr(srv, "_wall_time_ns", lambda: wall_now)
    monkeypatch.setattr(srv, "_monotonic_ns", lambda: mono_now["value"])
    server = LSPServer(root=tmp_path)
    _init(server)
    _rewrite_same_size_with_restored_mtime(tmp_path, "mod.py", before, after)
    mono_now["value"] += srv._CONTENT_RECHECK_NS + 1
    assert server.is_stale() is True


def test_clock_rollback_does_not_extend_metadata_cache(tmp_path, monkeypatch):
    import index_graph.lsp.server as srv

    before = "def foo():\n    pass\ndef bar():\n    foo()\n"
    after = "def foo():\n    pass\ndef bar():\n    baz()\n"
    write(tmp_path, "mod.py", before)
    file_mtime = 1_700_000_000_000_000_000
    os.utime(tmp_path / "mod.py", ns=(file_mtime, file_mtime))
    wall_now = {"value": file_mtime + srv._MTIME_UNCERTAINTY_NS + 10_000_000_000}
    mono_now = {"value": 100_000_000_000}
    monkeypatch.setattr(srv, "_wall_time_ns", lambda: wall_now["value"])
    monkeypatch.setattr(srv, "_monotonic_ns", lambda: mono_now["value"])
    server = LSPServer(root=tmp_path)
    _init(server)
    _rewrite_same_size_with_restored_mtime(tmp_path, "mod.py", before, after)
    wall_now["value"] -= 5_000_000_000
    mono_now["value"] += srv._CONTENT_RECHECK_NS + 1
    assert server.is_stale() is True


def test_references_on_stale_workspace_errors(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    uri = path_to_uri(tmp_path / "mod.py")
    write(tmp_path, "new.py", "def added():\n    pass\n")  # a new file appears
    r = server.handle_request({
        "jsonrpc": "2.0", "id": 11, "method": "textDocument/references",
        "params": {"textDocument": {"uri": uri}, "position": {"line": 0, "character": 4},
                   "context": {"includeDeclaration": False}}})
    assert "error" in r
    assert r["error"]["code"] == STALE_CODE


def test_reinitialize_clears_staleness(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n")
    server = LSPServer(root=tmp_path)
    _init(server)
    write(tmp_path, "mod.py", "def foo():\n    pass\ndef bar():\n    foo()\n    foo()\n")
    assert server.is_stale() is True
    # IDE re-initializes; the graph and fingerprint are rebuilt fresh
    _init(server)
    assert server.is_stale() is False
