from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Event, Thread

import pytest

from index_graph import router, router_jobs


def _job(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "solo" / ".git").mkdir(parents=True)
    return router_jobs.create_router_job(
        workspace, job_root=tmp_path / "jobs", executor="thread", use_cache=False
    )


def _events(job):
    return [json.loads(line) for line in
            (Path(job["job_dir"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("render_fails", [False, True])
def test_graph_completion_is_not_job_completion_while_renderer_waits(tmp_path, monkeypatch, render_fails):
    job = _job(tmp_path)
    entered = Event()
    release = Event()
    original_render = router.render_router
    original_append = router_jobs._append_event
    accepted_results = []
    exits = []

    def observe_append(job_dir, event):
        if event["phase"] == "complete":
            accepted_results.append(router_jobs.read_router_job_result(
                job["job_id"], job_root=tmp_path / "jobs"))
        original_append(job_dir, event)

    def delayed_render(*args, **kwargs):
        entered.set()
        if not release.wait(10):
            raise TimeoutError("test did not release renderer")
        if render_fails:
            raise ValueError("synthetic renderer failure")
        return original_render(*args, **kwargs)

    monkeypatch.setattr(router_jobs, "_append_event", observe_append)
    monkeypatch.setattr(router, "render_router", delayed_render)
    worker = Thread(target=lambda: exits.append(router_jobs.run_router_job_worker(job["job_dir"])))
    worker.start()
    try:
        assert entered.wait(10)
        status = router_jobs.read_router_job_status(job["job_id"], job_root=tmp_path / "jobs")
        result = router_jobs.read_router_job_result(job["job_id"], job_root=tmp_path / "jobs")
        assert status["status"] == "running"
        assert "content" not in result
        events = _events(job)
        assert not any(event["phase"] == "complete" for event in events)
        graph_done = [event for event in events if event["phase"] == "graph_complete"]
        assert len(graph_done) == 1
        assert graph_done[0]["scope"] == "graph"
        assert graph_done[0]["graph_phase"] == "complete"
        assert graph_done[0]["status"] == "running"
        assert graph_done[0]["terminal"] is False
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive()
    assert exits == [1 if render_fails else 0]
    events = _events(job)
    terminal = [event for event in events if event.get("terminal")]
    assert len(terminal) == 1
    assert terminal[0]["scope"] == "job"
    assert terminal[0]["status"] == ("failed" if render_fails else "complete")
    assert terminal[0]["phase"] == terminal[0]["status"]
    if render_fails:
        assert not accepted_results
        result = router_jobs.read_router_job_result(job["job_id"], job_root=tmp_path / "jobs")
        assert result["status"] == "failed"
        assert "content" not in result
    else:
        assert len(accepted_results) == 1
        assert accepted_results[0]["status"] == "complete"
        assert accepted_results[0]["content"].startswith("# Workspace map")
        assert accepted_results[0]["result_sha256"]


def test_job_event_clock_includes_pre_graph_work_and_buffered_timings(tmp_path, monkeypatch):
    job = _job(tmp_path)
    original_config = router_jobs._config_sha256

    def delayed_config(root):
        time.sleep(0.06)
        return original_config(root)

    monkeypatch.setattr(router_jobs, "_config_sha256", delayed_config)
    assert router_jobs.run_router_job_worker(job["job_dir"]) == 0
    events = _events(job)
    first_graph = next(event for event in events if event["phase"] == "building")
    assert first_graph["elapsed_ms"] >= 50
    assert first_graph["graph_elapsed_ms"] < first_graph["elapsed_ms"]
    elapsed = [event["elapsed_ms"] for event in events]
    assert elapsed == sorted(elapsed), "buffered timings must not reset the emitted job clock"
    assert len({event["run_token"] for event in events}) == 1
    assert all(event["elapsed_clock"] == "worker_monotonic" for event in events)
    timings = [event for event in events if event["phase"] == "timing"]
    assert timings
    assert all(event["scope"] == "stage" and event["duration_ms"] >= 0 for event in timings)


def test_graph_failure_is_scoped_before_job_failure_is_committed(tmp_path, monkeypatch):
    job = _job(tmp_path)

    def fail_graph(*args, on_progress, **kwargs):
        on_progress(router_jobs.GraphProgress("failed", 0, 1, 0))
        raise ValueError("synthetic graph failure")

    monkeypatch.setattr(router_jobs, "build_graph", fail_graph)
    assert router_jobs.run_router_job_worker(job["job_dir"]) == 1
    events = _events(job)
    graph_failed, job_failed = events
    assert graph_failed["phase"] == "graph_failed"
    assert graph_failed["graph_phase"] == "failed"
    assert graph_failed["scope"] == "graph"
    assert graph_failed["terminal"] is False
    assert job_failed["phase"] == job_failed["status"] == "failed"
    assert job_failed["scope"] == "job"
    assert job_failed["terminal"] is True


def test_rejected_worker_does_not_claim_job_failed(tmp_path):
    job = _job(tmp_path)
    # A token is assigned on worker startup. Give this queued job an owner so
    # the independent stale-worker rejection path is exercised directly.
    job_dir = Path(job["job_dir"])
    status = router_jobs._read_status_file(job_dir)
    status["run_token"] = "current-owner"
    router_jobs._write_status(job_dir, status)
    assert router_jobs.run_router_job_worker(job_dir, "stale-owner") == 1
    [event] = _events(job)
    assert event["scope"] == "attempt"
    assert event["status"] == "failed"
    assert event["run_token"] == "stale-owner"
    assert event["terminal"] is True
    assert router_jobs._read_status_file(job_dir)["status"] == status["status"]


def test_duplicate_live_worker_has_distinct_event_clock_identity(tmp_path, monkeypatch):
    job = _job(tmp_path)
    entered, release = Event(), Event()
    original_render = router.render_router
    exits = []

    def delayed_render(*args, **kwargs):
        entered.set()
        if not release.wait(10):
            raise TimeoutError("test did not release renderer")
        return original_render(*args, **kwargs)

    monkeypatch.setattr(router, "render_router", delayed_render)
    worker = Thread(target=lambda: exits.append(router_jobs.run_router_job_worker(job["job_dir"])))
    worker.start()
    try:
        assert entered.wait(10)
        job_dir = Path(job["job_dir"])
        status_path = job_dir / "status.json"
        before = status_path.read_bytes()
        run_token = json.loads(before)["run_token"]
        assert router_jobs.run_router_job_worker(job_dir, run_token) == 1
        assert status_path.read_bytes() == before
        rejected = [event for event in _events(job) if event["scope"] == "attempt"]
        assert len(rejected) == 1
        assert rejected[0]["status"] == "failed"
        result = router_jobs.read_router_job_result(job["job_id"], job_root=tmp_path / "jobs")
        assert "content" not in result
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive()
    assert exits == [0]
    events = _events(job)
    assert len({event["run_token"] for event in events}) == 1
    emitters = {event["worker_instance_id"] for event in events}
    assert len(emitters) == 2
    for emitter in emitters:
        elapsed = [event["elapsed_ms"] for event in events if event["worker_instance_id"] == emitter]
        assert elapsed == sorted(elapsed)
    owner = next(event for event in events if event["phase"] == "complete")
    assert owner["worker_instance_id"] != rejected[0]["worker_instance_id"]
    assert router_jobs.read_router_job_result(job["job_id"], job_root=tmp_path / "jobs")["status"] == "complete"
