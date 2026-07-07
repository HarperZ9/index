"""Falsifiers for index watch — the auto-resync feature.

Load-bearing: the watcher must (1) detect a real content change and emit a
STALE receipt naming the changed repo, (2) stay silent on FRESH ticks (only
movement is reported), (3) produce a receipt a third party re-derives with the
pure compare, and (4) survive a rescan error without crashing the loop.
Deterministic: injected sleep/clock, bounded ticks — no real waiting.
"""
from __future__ import annotations

import json

import pytest

from index_graph.freshness.compare import compare_freshness
from index_graph.freshness.fingerprint import workspace_fingerprint
from index_graph.freshness.watch import SYNC_SCHEMA, sync_report, watch_iter


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "alpha"
    r.mkdir()
    (r / "package.json").write_text('{"name":"alpha","version":"0.0.1"}',
                                    encoding="utf-8")
    return {"alpha": r}


def _mutations(*edits):
    """A sleep() that applies one queued edit per tick, so the fingerprint
    changes deterministically between polls without real time passing."""
    q = list(edits)

    def _sleep(_interval):
        if q:
            q.pop(0)()
    return _sleep


def test_baseline_then_detects_a_real_change(repo):
    alpha = repo["alpha"]

    def edit():
        (alpha / "index.js").write_text("import './x.js'\n", encoding="utf-8")

    reports = list(watch_iter(repo, interval=1, max_ticks=3,
                              sleep=_mutations(edit),
                              clock=lambda: 0.0))
    assert reports[0]["tick"] == 0 and reports[0]["verdict"] == "FRESH"  # baseline
    stale = [r for r in reports if r["tick"] > 0]
    assert len(stale) == 1, "exactly one change happened -> one STALE receipt"
    assert stale[0]["verdict"] == "STALE"
    assert "alpha" in stale[0]["repos_changed"]


def test_fresh_ticks_are_silent(repo):
    # no edits: only the baseline is ever yielded, however many ticks elapse
    reports = list(watch_iter(repo, interval=1, max_ticks=5,
                              sleep=lambda _i: None, clock=lambda: 0.0))
    assert [r["tick"] for r in reports] == [0]


def test_receipt_is_rederivable(repo, tmp_path):
    prev = workspace_fingerprint(repo)
    (repo["alpha"] / "pyproject.toml").write_text(
        '[project]\nname="alpha"\ndependencies=["beta"]\n', encoding="utf-8")
    curr = workspace_fingerprint(repo)
    report = sync_report(prev, curr, tick=1, at=0.0)
    assert report["schema"] == SYNC_SCHEMA
    # a third party recomputes the verdict from the two fingerprints
    independent = compare_freshness(prev, curr)
    assert report["verdict"] == independent["verdict"] == "STALE"
    assert report["repos_changed"] == independent["repos_changed"]


def test_added_and_removed_repos_are_named(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "package.json").write_text('{"name":"a"}', encoding="utf-8")
    paths = {"a": a}

    def add_b():
        b = tmp_path / "b"
        b.mkdir()
        (b / "package.json").write_text('{"name":"b"}', encoding="utf-8")
        paths["b"] = b

    reports = list(watch_iter(paths, interval=1, max_ticks=2,
                              sleep=_mutations(add_b), clock=lambda: 0.0))
    stale = [r for r in reports if r["tick"] > 0]
    assert stale and stale[0]["repos_added"] == ["b"]


def test_rescan_error_does_not_crash_the_loop(repo, monkeypatch):
    import index_graph.freshness.watch as W

    calls = {"n": 0}
    real = W.workspace_fingerprint

    def flaky(paths, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:                      # second call (first tick) explodes
            raise OSError("transient FS error")
        return real(paths, *a, **k)

    monkeypatch.setattr(W, "workspace_fingerprint", flaky)
    reports = list(watch_iter(repo, interval=1, max_ticks=2,
                              sleep=lambda _i: None, clock=lambda: 0.0))
    errored = [r for r in reports if r.get("verdict") == "UNVERIFIABLE"]
    assert errored, "an errored rescan must be reported, not raised"
    assert errored[0]["error"]


def test_cli_watch_json_bounded(repo, tmp_path, capsys):
    from index_graph.cli_handlers.verify import cmd_watch

    alpha = repo["alpha"]
    (alpha / "extra.py").write_text("import os\n", encoding="utf-8")  # pre-change

    class Args:
        root = list(repo.values())[0].parent
        interval = 0.001
        max_ticks = 1
        regen = None
        out = None
        json = True

    assert cmd_watch(Args()) == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    baseline = json.loads(lines[0])
    assert baseline["schema"] == SYNC_SCHEMA and baseline["tick"] == 0
