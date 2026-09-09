from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Thread

import pytest

from index_graph import router_jobs

_REAL_POPEN = subprocess.Popen


def _repo(root: Path, name: str) -> Path:
    repo = root / name
    (repo / ".git").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        f"[project]\nname='{name}'\nversion='0'\n", encoding="utf-8"
    )
    return repo


def _text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


def _write_status(job_dir: Path, status: dict) -> None:
    status = {**status, "schema": "index.router-job-status/v1", "job_id": job_dir.name}
    (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")


@contextmanager
def _held_byte_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+b")
    fh.seek(0)
    if fh.read(1) == b"":
        fh.write(b"0")
        fh.flush()
    fh.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield fh
        finally:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            fh.close()
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield fh
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


@contextmanager
def _held_external_byte_lock(path: Path):
    script = r"""
import os
import sys

path = sys.argv[1]
fh = open(path, "a+b")
fh.seek(0, os.SEEK_END)
if fh.tell() == 0:
    fh.seek(0)
    fh.write(b"0")
    fh.flush()
fh.seek(0)
if os.name == "nt":
    import msvcrt

    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    print("locked", flush=True)
    sys.stdin.readline()
    fh.seek(0)
    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    print("locked", flush=True)
    sys.stdin.readline()
    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
fh.close()
"""
    proc = _REAL_POPEN(
        [sys.executable, "-c", script, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "locked"
    try:
        yield proc
    finally:
        if proc.stdin is not None:
            proc.stdin.write("\n")
            proc.stdin.flush()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_start_records_guarded_hidden_worker_command(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job_root = tmp_path / "jobs"
    calls = []

    class FakeProcess:
        pid = 4242

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    receipt = router_jobs.start_router_job(workspace, job_root=job_root, max_docs=7)

    assert receipt["schema"] == "index.router-job-status/v1"
    assert receipt["status"] == "running"
    assert receipt["job_id"]
    assert receipt["max_docs"] == 7
    assert receipt["pid"] == 4242
    assert calls, "start must spawn exactly one worker"
    args, kwargs = calls[0]
    assert args[:3] == [sys.executable, "-m", "index_graph.router_jobs"]
    assert args[3] == "_worker"
    assert Path(args[4]).name == receipt["job_id"]
    assert args[5] == receipt["run_token"]
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert kwargs.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW
    status_path = job_root / receipt["job_id"] / "status.json"
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "running"


def test_start_spawn_failure_marks_failed_in_state(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job_root = tmp_path / "jobs"

    def fail_popen(args, **kwargs):
        raise OSError("spawn refused")

    monkeypatch.setattr(subprocess, "Popen", fail_popen)

    receipt = router_jobs.start_router_job(workspace, job_root=job_root)

    assert receipt["status"] == "failed"
    assert receipt["phase"] == "failed"
    assert receipt["error_type"] == "OSError"
    status = router_jobs.read_router_job_status(receipt["job_id"], job_root=job_root)
    assert status["status"] == "failed"
    result = router_jobs.read_router_job_result(receipt["job_id"], job_root=job_root)
    assert result["status"] == "failed"
    assert "content" not in result


def test_worker_writes_complete_result_after_full_router_success(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    monkeypatch.setenv("INDEX_ROUTER_JOB_DIR", str(job_root))

    job = router_jobs.create_router_job(workspace, job_root=job_root, max_docs=3)
    exit_code = router_jobs.run_router_job_worker(job["job_dir"])

    assert exit_code == 0
    status = router_jobs.read_router_job_status(job["job_id"], job_root=job_root)
    assert status["status"] == "complete"
    assert status["phase"] == "complete"
    assert status["completed_repos"] == status["total_repos"] == 1
    assert status["result_sha256"]
    assert status["request_sha256"]
    assert status["config_sha256"]
    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)
    assert result["status"] == "complete"
    assert result["result_sha256"] == status["result_sha256"]
    assert result["request_sha256"] == status["request_sha256"]
    assert result["content"].startswith("# Workspace map")
    assert "solo" in result["content"]
    events = [json.loads(line) for line in (Path(job["job_dir"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[0]["phase"] == "building"
    assert events[-1]["phase"] == "complete"


def test_failed_worker_never_reports_complete_and_result_is_receipt(tmp_path):
    workspace = tmp_path / "missing"
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)

    exit_code = router_jobs.run_router_job_worker(job["job_dir"])

    assert exit_code == 1
    status = router_jobs.read_router_job_status(job["job_id"], job_root=job_root)
    assert status["status"] == "failed"
    assert status["phase"] == "failed"
    assert status["error_type"]
    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)
    assert result["schema"] == "index.router-job-result/v1"
    assert result["status"] == "failed"
    assert "content" not in result


def test_worker_graph_source_error_marks_failed_without_result(tmp_path, monkeypatch):
    from index_graph.graph.walk import GraphSourceError

    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)

    def fail_graph(*args, **kwargs):
        raise GraphSourceError("graph source read failed: 'x.py' (OSError)")

    monkeypatch.setattr(router_jobs, "build_graph", fail_graph)

    exit_code = router_jobs.run_router_job_worker(job["job_dir"])
    status = router_jobs.read_router_job_status(job["job_id"], job_root=job_root)
    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)

    assert exit_code == 1
    assert status["status"] == "failed"
    assert status["error_type"] == "GraphSourceError"
    assert status["result_available"] is False
    assert not (Path(job["job_dir"]) / "router.md").exists()
    assert result["status"] == "failed"
    assert result["result_available"] is False
    assert "content" not in result


def test_result_refuses_partial_output_until_status_complete(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    job_dir = Path(job["job_dir"])
    (job_dir / "router.md").write_text("# partial\n", encoding="utf-8")

    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)

    assert result["status"] == "running"
    assert result["result_available"] is False
    assert "content" not in result


def test_result_refuses_corrupt_complete_output(tmp_path):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    assert router_jobs.run_router_job_worker(job["job_dir"]) == 0
    job_dir = Path(job["job_dir"])
    (job_dir / "router.md").write_text("# tampered\n", encoding="utf-8")

    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)

    assert result["status"] == "failed"
    assert result["error_type"] == "CorruptResult"
    assert result["result_available"] is False
    assert "content" not in result


def test_stale_worker_cannot_overwrite_newer_complete_result(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    job_dir = Path(job["job_dir"])
    stale_token = "stale-token"
    newer_token = "newer-token"
    newer_text = "# Workspace map\n\nnewer complete result\n"
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    status["run_token"] = stale_token
    _write_status(job_dir, status)

    def render_newer_then_return_stale(pack, max_docs):
        current = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
        current.update(
            {
                "status": "complete",
                "phase": "complete",
                "run_token": newer_token,
                "result_available": True,
                "result_path": str(job_dir / "router.md"),
                "result_sha256": _text_sha256(newer_text),
                "result_bytes": len(newer_text.encode("utf-8", "surrogateescape")),
                "finished_at": "2026-09-07T00:00:00-07:00",
            }
        )
        (job_dir / "router.md").write_text(newer_text, encoding="utf-8")
        _write_status(job_dir, current)
        return "# stale worker output\n"

    monkeypatch.setattr("index_graph.router.render_router", render_newer_then_return_stale)

    assert router_jobs.run_router_job_worker(job["job_dir"], stale_token) == 1

    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)
    assert result["status"] == "complete"
    assert result["content"] == newer_text
    assert (job_dir / "router.md").read_text(encoding="utf-8") == newer_text


@pytest.mark.parametrize("mutation", ["delete", "tamper"])
def test_complete_result_requires_matching_persisted_request_seal(tmp_path, mutation):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    other = tmp_path / "other"
    other.mkdir()
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    assert router_jobs.run_router_job_worker(job["job_dir"]) == 0
    job_dir = Path(job["job_dir"])
    request_path = job_dir / "request.json"
    if mutation == "delete":
        request_path.unlink()
    else:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request["root"] = str(other)
        request_path.write_text(json.dumps(request), encoding="utf-8")

    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)

    assert result["status"] == "failed"
    assert result["result_available"] is False
    assert result["error_type"] == "RequestSealInvalid"
    assert "content" not in result


def test_complete_result_rejects_symlink_result_file(tmp_path):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    assert router_jobs.run_router_job_worker(job["job_dir"]) == 0
    job_dir = Path(job["job_dir"])
    private_text = "private target content\n"
    private_file = tmp_path / "private.txt"
    private_file.write_text(private_text, encoding="utf-8")
    result_path = job_dir / "router.md"
    result_path.unlink()
    try:
        result_path.symlink_to(private_file)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    status["result_sha256"] = _text_sha256(private_text)
    status["result_bytes"] = len(private_text.encode("utf-8", "surrogateescape"))
    _write_status(job_dir, status)

    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)

    assert result["status"] == "failed"
    assert result["error_type"] == "UnsafeResult"
    assert result["result_available"] is False
    assert "content" not in result


def test_cancel_marks_only_the_requested_owned_job(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job_root = tmp_path / "jobs"
    first = router_jobs.create_router_job(workspace, job_root=job_root)
    second = router_jobs.create_router_job(workspace, job_root=job_root)

    cancelled = router_jobs.cancel_router_job(first["job_id"], job_root=job_root)

    assert cancelled["status"] == "cancellation_requested"
    assert (Path(first["job_dir"]) / "cancel.request").is_file()
    assert not (Path(second["job_dir"]) / "cancel.request").exists()
    assert router_jobs.read_router_job_status(second["job_id"], job_root=job_root)["status"] == "running"


def test_worker_acknowledges_cancel_marker_without_result(tmp_path):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    router_jobs.cancel_router_job(job["job_id"], job_root=job_root)

    exit_code = router_jobs.run_router_job_worker(job["job_dir"])

    assert exit_code == 2
    status = router_jobs.read_router_job_status(job["job_id"], job_root=job_root)
    assert status["status"] == "cancelled"
    assert status["phase"] == "cancelled"
    assert router_jobs.read_router_job_result(job["job_id"], job_root=job_root)["result_available"] is False


def test_worker_cancels_during_inventory_without_graph_or_result(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _repo(workspace, "a")
    _repo(workspace, "z")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)

    import index_graph.router_inventory as inventory_mod

    real_walk = inventory_mod.os.walk
    cancellation_sent = {"value": False}

    def cancel_before_second_repo(*args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(*args, **kwargs):
            if Path(dirpath).name == "z" and not cancellation_sent["value"]:
                router_jobs.cancel_router_job(job["job_id"], job_root=job_root)
                cancellation_sent["value"] = True
            yield dirpath, dirnames, filenames

    def graph_after_inventory_cancel(*args, **kwargs):
        pytest.fail("graph phase must not run after inventory cancellation")

    monkeypatch.setattr(inventory_mod.os, "walk", cancel_before_second_repo)
    monkeypatch.setattr(router_jobs, "build_graph", graph_after_inventory_cancel)

    exit_code = router_jobs.run_router_job_worker(job["job_dir"])
    status = router_jobs.read_router_job_status(job["job_id"], job_root=job_root)
    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)

    assert cancellation_sent["value"] is True
    assert exit_code == 2
    assert status["status"] == "cancelled"
    assert status["phase"] == "cancelled"
    assert "router_inventory" not in status
    assert result["status"] == "cancelled"
    assert result["result_available"] is False
    assert "content" not in result


def test_cancel_terminate_does_not_use_pid_as_authority(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    job_dir = Path(job["job_dir"])
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    status["pid"] = 12345
    status["run_token"] = "owned-token"
    (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")

    def fail_kill(pid, sig):
        raise AssertionError("PID-only hard termination must not be attempted")

    monkeypatch.setattr(os, "kill", fail_kill)

    receipt = router_jobs.cancel_router_job(job["job_id"], job_root=job_root, terminate=True)

    assert receipt["status"] == "cancellation_requested"
    assert receipt["termination_supported"] is False
    assert receipt["result_available"] is False


def test_cancel_preserves_completion_written_after_stale_read(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    job_dir = Path(job["job_dir"])
    complete_text = "# Workspace map\n\ncompleted before cancel write\n"
    original_atomic_write_json = router_jobs._atomic_write_json

    def interleave_complete_after_cancel_marker(path, data):
        original_atomic_write_json(path, data)
        if Path(path).name == "cancel.request":
            current = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            current.update(
                {
                    "status": "complete",
                    "phase": "complete",
                    "result_available": True,
                    "result_path": str(job_dir / "router.md"),
                    "result_sha256": _text_sha256(complete_text),
                    "result_bytes": len(complete_text.encode("utf-8", "surrogateescape")),
                    "finished_at": "2026-09-07T00:00:00-07:00",
                }
            )
            (job_dir / "router.md").write_text(complete_text, encoding="utf-8")
            original_atomic_write_json(job_dir / "status.json", current)

    monkeypatch.setattr(router_jobs, "_atomic_write_json", interleave_complete_after_cancel_marker)

    receipt = router_jobs.cancel_router_job(job["job_id"], job_root=job_root)

    assert receipt["status"] == "complete"
    assert router_jobs.read_router_job_result(job["job_id"], job_root=job_root)["content"] == complete_text


def test_worker_revalidates_repo_universe_on_each_attempt(tmp_path):
    workspace = tmp_path / "workspace"
    _repo(workspace, "first")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    _repo(workspace, "second")

    assert router_jobs.run_router_job_worker(job["job_dir"]) == 0

    status = router_jobs.read_router_job_status(job["job_id"], job_root=job_root)
    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)
    assert status["total_repos"] == 2
    assert "first" in result["content"]
    assert "second" in result["content"]


def test_resume_does_not_spawn_duplicate_for_active_lease(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    job_dir = Path(job["job_dir"])
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    token = "active-token"
    status["run_token"] = token
    status["pid"] = 12345
    (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    lease = {
        "schema": "index.router-job-lease/v1",
        "job_id": job["job_id"],
        "run_token": token,
        "pid": 12345,
        "started_epoch": time.time(),
    }
    heartbeat = {**lease, "schema": "index.router-job-heartbeat/v1", "updated_epoch": time.time()}
    (job_dir / "worker.lock").write_text(json.dumps(lease), encoding="utf-8")
    (job_dir / "worker.heartbeat.json").write_text(json.dumps(heartbeat), encoding="utf-8")

    def fail_popen(args, **kwargs):
        raise AssertionError("active leased job must not spawn a duplicate worker")

    monkeypatch.setattr(subprocess, "Popen", fail_popen)

    with _held_external_byte_lock(job_dir / "worker.lock"):
        receipt = router_jobs.resume_router_job(job["job_id"], job_root=job_root)

    assert receipt["status"] == "running"
    assert receipt["run_token"] == token
    assert receipt["attempt"] == 1


def test_resume_does_not_spawn_duplicate_when_real_worker_lock_is_held(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    job_dir = Path(job["job_dir"])
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    token = "active-token"
    status["run_token"] = token
    status["pid"] = 12345
    status["worker_started_epoch"] = time.time() - 3600
    _write_status(job_dir, status)
    lease = {
        "schema": "index.router-job-lease/v1",
        "job_id": job["job_id"],
        "run_token": token,
        "pid": 12345,
        "started_epoch": time.time() - 3600,
    }
    heartbeat = {
        **lease,
        "schema": "index.router-job-heartbeat/v1",
        "updated_epoch": time.time() - 3600,
    }
    (job_dir / "worker.lock").write_text(json.dumps(lease), encoding="utf-8")
    (job_dir / "worker.heartbeat.json").write_text(json.dumps(heartbeat), encoding="utf-8")

    def fail_popen(args, **kwargs):
        raise AssertionError("held worker lock must prevent duplicate resume spawn")

    monkeypatch.setattr(subprocess, "Popen", fail_popen)

    with _held_external_byte_lock(job_dir / "worker.lock"):
        receipt = router_jobs.resume_router_job(job["job_id"], job_root=job_root)

    assert receipt["status"] == "running"
    assert receipt["run_token"] == token
    assert receipt["attempt"] == 1


def test_simultaneous_resumes_spawn_one_worker(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    job_dir = Path(job["job_dir"])
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    status["status"] = "failed"
    status["phase"] = "failed"
    status["error_type"] = "WorkerInterrupted"
    _write_status(job_dir, status)
    calls = []
    barrier = Barrier(2)

    class FakeProcess:
        pid = 4343

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        try:
            barrier.wait(timeout=1)
        except Exception:
            pass
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    results = []
    threads = [
        Thread(target=lambda: results.append(router_jobs.resume_router_job(job["job_id"], job_root=job_root)))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert len(results) == 2
    assert len(calls) == 1
    assert {result["run_token"] for result in results} == {results[0]["run_token"]}


def test_start_does_not_overwrite_fast_terminal_worker_state(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job_root = tmp_path / "jobs"

    class FakeProcess:
        pid = 5151

    def fake_popen(args, **kwargs):
        job_dir = Path(args[4])
        status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
        status["status"] = "failed"
        status["phase"] = "failed"
        status["error_type"] = "FastFailure"
        status["message"] = "worker finished before parent pid write"
        (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    receipt = router_jobs.start_router_job(workspace, job_root=job_root)

    assert receipt["status"] == "failed"
    assert receipt["error_type"] == "FastFailure"


def test_resume_restarts_stale_running_job_without_claiming_complete(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _repo(workspace, "solo")
    job_root = tmp_path / "jobs"
    job = router_jobs.create_router_job(workspace, job_root=job_root)
    job_dir = Path(job["job_dir"])
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    status["pid"] = 999999999
    status["status"] = "running"
    status["run_token"] = "stale-token"
    (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    calls = []

    class FakeProcess:
        pid = 4343

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    receipt = router_jobs.resume_router_job(job["job_id"], job_root=job_root)

    assert receipt["status"] == "running"
    assert receipt["attempt"] == 2
    assert receipt["pid"] == 4343
    assert receipt["run_token"] != "stale-token"
    assert calls
    result = router_jobs.read_router_job_result(job["job_id"], job_root=job_root)
    assert result["status"] in {"running", "failed"}
    assert result["status"] != "complete"
    assert "content" not in result
