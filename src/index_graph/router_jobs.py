"""Durable local jobs for complete workspace router builds.

This module is intentionally independent from the CLI/MCP wiring. It owns the
private local job state and runs the existing router pipeline in a child process
so timeout-bound callers can start, poll, and fetch complete results without
receiving partial router content.
"""
from __future__ import annotations

import json
import os
import subprocess
import stat
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, BinaryIO

from . import __version__
from .graph.build import GraphProgress, build_graph

_STATUS_SCHEMA = "index.router-job-status/v1"
_RESULT_SCHEMA = "index.router-job-result/v1"
_REQUEST_SCHEMA = "index.router-job-request/v1"
_EVENT_SCHEMA = "index.router-job-event/v1"
_CANCEL_SCHEMA = "index.router-job-cancel/v1"
_CANCEL_FILE = "cancel.request"
_STATE_LOCK_FILE = "state.lock"
_STATUS_FILE = "status.json"
_REQUEST_FILE = "request.json"
_RESULT_FILE = "router.md"
_EVENTS_FILE = "events.jsonl"
_LEASE_FILE = "worker.lock"
_HEARTBEAT_FILE = "worker.heartbeat.json"
_LEASE_SCHEMA = "index.router-job-lease/v1"
_HEARTBEAT_SCHEMA = "index.router-job-heartbeat/v1"
_LOCK_BYTE_COUNT = 1
_WINDOWS_REPARSE_ATTRIBUTE = 0x400
_STATE_LOCKS = threading.local()
_STATE_THREAD_LOCKS: dict[str, threading.RLock] = {}
_STATE_THREAD_LOCKS_GUARD = threading.Lock()


class RouterJobError(ValueError):
    """Raised for invalid local job operations."""


class RouterJobCancelled(RuntimeError):
    """Internal cooperative cancellation signal."""


class RouterJobLostOwnership(RuntimeError):
    """Internal signal for a stale worker attempt that must not write status."""


class RouterJobAlreadyActive(RuntimeError):
    """Internal signal for a duplicate worker when the active lease is fresh."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _root_hash(root: Path) -> str:
    import hashlib

    return hashlib.sha256(str(root.resolve()).encode("utf-8", "surrogateescape")).hexdigest()[:16]


def _ensure_lock_byte(fh: BinaryIO) -> None:
    fh.seek(0, os.SEEK_END)
    if fh.tell() == 0:
        fh.seek(0)
        fh.write(b"0")
        fh.flush()
    fh.seek(0)


def _lock_handle(fh: BinaryIO, *, blocking: bool) -> None:
    if os.name == "nt":
        import msvcrt

        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        msvcrt.locking(fh.fileno(), mode, _LOCK_BYTE_COUNT)
        return
    import fcntl

    flags = fcntl.LOCK_EX
    if not blocking:
        flags |= fcntl.LOCK_NB
    fcntl.flock(fh.fileno(), flags)


def _unlock_handle(fh: BinaryIO) -> None:
    fh.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, _LOCK_BYTE_COUNT)
        except OSError:
            pass
        return
    import fcntl

    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def _locked_file(path: Path, *, blocking: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+b")
    locked = False
    try:
        _ensure_lock_byte(fh)
        _lock_handle(fh, blocking=blocking)
        locked = True
        yield fh
    finally:
        if locked:
            _unlock_handle(fh)
        fh.close()


@contextmanager
def _state_lock(job_dir: Path):
    lock_path = job_dir / _STATE_LOCK_FILE
    key = str(lock_path.resolve())
    held = getattr(_STATE_LOCKS, "held", None)
    if held is None:
        held = set()
        _STATE_LOCKS.held = held
    if key in held:
        yield
        return
    with _STATE_THREAD_LOCKS_GUARD:
        thread_lock = _STATE_THREAD_LOCKS.setdefault(key, threading.RLock())
    with thread_lock:
        with _locked_file(lock_path):
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)


def _sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8", "surrogateescape"))


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _request_sha256(request: dict[str, Any]) -> str:
    stable = dict(request)
    return _sha256_text(_canonical_json(stable))


def _config_sha256(root: Path) -> str:
    parts: list[list[str]] = []
    for name in (".index.toml", ".repomap.toml"):
        path = root / name
        if not path.exists():
            parts.append([name, "missing"])
            continue
        try:
            parts.append([name, _sha256_bytes(path.read_bytes())])
        except OSError:
            parts.append([name, "unreadable"])
    return _sha256_text(_canonical_json({"root": str(root.resolve()), "config": parts}))


def _heartbeat_stale_seconds() -> float:
    raw = os.environ.get("INDEX_ROUTER_JOB_HEARTBEAT_STALE_SECONDS", "60")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def _is_terminal(status: dict[str, Any]) -> bool:
    return status.get("status") in {"complete", "failed", "cancelled"}


def default_job_root() -> Path:
    raw = os.environ.get("INDEX_ROUTER_JOB_DIR")
    if raw:
        return Path(raw)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "index_graph" / "router-jobs"
    return Path.home() / ".cache" / "index_graph" / "router-jobs"


def _job_root(job_root: Path | str | None = None) -> Path:
    return Path(job_root) if job_root is not None else default_job_root()


def _validate_job_id(job_id: str) -> str:
    try:
        parsed = uuid.UUID(str(job_id))
    except ValueError as exc:
        raise RouterJobError("invalid router job id") from exc
    return str(parsed)


def _job_dir(job_id: str, job_root: Path | str | None = None) -> Path:
    return _job_root(job_root) / _validate_job_id(job_id)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    tmp.replace(path)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RouterJobError(f"cannot read router job state: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise RouterJobError(f"invalid router job state: {path.name}") from exc
    if not isinstance(data, dict):
        raise RouterJobError(f"invalid router job state: {path.name}")
    return data


def _read_request(job_dir: Path) -> dict[str, Any]:
    data = _read_json(job_dir / _REQUEST_FILE)
    if data.get("schema") != _REQUEST_SCHEMA:
        raise RouterJobError("invalid router job request schema")
    if data.get("job_id") != job_dir.name:
        raise RouterJobError("router job request id mismatch")
    return data


def _read_status_file_unlocked(job_dir: Path) -> dict[str, Any]:
    data = _read_json(job_dir / _STATUS_FILE)
    if data.get("schema") != _STATUS_SCHEMA:
        raise RouterJobError("invalid router job status schema")
    if data.get("job_id") != job_dir.name:
        raise RouterJobError("router job status id mismatch")
    return data


def _read_status_file(job_dir: Path) -> dict[str, Any]:
    with _state_lock(job_dir):
        return _read_status_file_unlocked(job_dir)


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_status_unlocked(job_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    status = dict(status)
    status["schema"] = _STATUS_SCHEMA
    status["job_id"] = job_dir.name
    status["updated_at"] = _now()
    _atomic_write_json(job_dir / _STATUS_FILE, status)
    return status


def _write_status(job_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    with _state_lock(job_dir):
        return _write_status_unlocked(job_dir, status)


def _append_event(job_dir: Path, event: dict[str, Any]) -> None:
    rec = {"schema": _EVENT_SCHEMA, "job_id": job_dir.name, "recorded_at": _now(), **event}
    with (job_dir / _EVENTS_FILE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")


def _write_heartbeat(job_dir: Path, run_token: str, *, started_epoch: float) -> None:
    payload = {
        "schema": _HEARTBEAT_SCHEMA,
        "job_id": job_dir.name,
        "run_token": run_token,
        "pid": os.getpid(),
        "started_epoch": started_epoch,
        "updated_epoch": time.time(),
    }
    _atomic_write_json(job_dir / _HEARTBEAT_FILE, payload)


def _start_heartbeat(job_dir: Path, run_token: str, *, started_epoch: float) -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(1.0):
            try:
                _write_heartbeat(job_dir, run_token, started_epoch=started_epoch)
            except OSError:
                pass

    _write_heartbeat(job_dir, run_token, started_epoch=started_epoch)
    thread = threading.Thread(target=beat, name="index-router-job-heartbeat", daemon=True)
    thread.start()
    return stop, thread


def _worker_lock_is_held(job_dir: Path) -> bool:
    lock_path = job_dir / _LEASE_FILE
    if not lock_path.exists():
        return False
    try:
        with _locked_file(lock_path, blocking=False):
            return False
    except OSError:
        return True


def _active_worker(status: dict[str, Any], job_dir: Path) -> bool:
    run_token = status.get("run_token")
    if not isinstance(run_token, str) or not run_token:
        return False
    return _worker_lock_is_held(job_dir)


def _acquire_lease(job_dir: Path, run_token: str) -> BinaryIO:
    lease_path = job_dir / _LEASE_FILE
    payload = {
        "schema": _LEASE_SCHEMA,
        "job_id": job_dir.name,
        "run_token": run_token,
        "pid": os.getpid(),
        "started_epoch": time.time(),
    }
    lock: BinaryIO | None = None
    try:
        lock = (job_dir / _LEASE_FILE).open("a+b")
        _ensure_lock_byte(lock)
        _lock_handle(lock, blocking=False)
    except OSError as exc:
        if lock is not None:
            lock.close()
        raise RouterJobAlreadyActive("router job already has an active worker lock") from exc
    lock.seek(0)
    lock.truncate()
    lock.write(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
    lock.flush()
    return lock


def _release_lease(job_dir: Path, run_token: str, lock: BinaryIO | None = None) -> None:
    if lock is not None:
        try:
            _unlock_handle(lock)
        finally:
            lock.close()


def _cancel_requested(job_dir: Path, run_token: str | None = None) -> bool:
    path = job_dir / _CANCEL_FILE
    if not path.exists():
        return False
    data = _read_json_if_present(path)
    if data is None:
        return True
    marker_token = data.get("run_token")
    return not marker_token or marker_token == run_token


def _recent_worker_start(status: dict[str, Any]) -> bool:
    try:
        started = float(status.get("worker_started_epoch"))
    except (TypeError, ValueError):
        return False
    return time.time() - started <= _heartbeat_stale_seconds()


def _fail_status(
    job_dir: Path,
    status: dict[str, Any],
    *,
    error_type: str,
    message: str,
) -> dict[str, Any]:
    failed = dict(status)
    failed["status"] = "failed"
    failed["phase"] = "failed"
    failed["error_type"] = error_type
    failed["message"] = message
    failed["result_available"] = False
    failed["finished_at"] = failed.get("finished_at") or _now()
    return _write_status_unlocked(job_dir, failed)


def _result_file_is_unsafe(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    if getattr(info, "st_file_attributes", 0) & _WINDOWS_REPARSE_ATTRIBUTE:
        return True
    return not stat.S_ISREG(info.st_mode)


def _read_regular_result_text(job_dir: Path) -> str:
    result_path = job_dir / _RESULT_FILE
    if _result_file_is_unsafe(result_path):
        raise RouterJobError("router job result path is a link, reparse point, or non-regular file")
    if not result_path.is_file():
        raise FileNotFoundError("router job result is missing")
    resolved_job = job_dir.resolve()
    resolved_result = result_path.resolve()
    if resolved_result.parent != resolved_job:
        raise RouterJobError("router job result path escapes its job directory")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(result_path), flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RouterJobError("router job result is not a regular file")
        with os.fdopen(fd, "r", encoding="utf-8", errors="surrogateescape", newline=None, closefd=False) as fh:
            return fh.read()
    finally:
        os.close(fd)


def _base_status(job_id: str, request: dict[str, Any], *, attempt: int) -> dict[str, Any]:
    return {
        "schema": _STATUS_SCHEMA,
        "job_id": job_id,
        "tool_version": __version__,
        "source_version": __version__,
        "root": request["root"],
        "root_sha256_prefix": request["root_sha256_prefix"],
        "max_docs": request["max_docs"],
        "budget_ms": request["budget_ms"],
        "use_cache": request["use_cache"],
        "executor": request["executor"],
        "status": "running",
        "phase": "queued",
        "completed_repos": 0,
        "total_repos": None,
        "attempt": attempt,
        "run_token": None,
        "pid": None,
        "worker_started_epoch": None,
        "request_sha256": _request_sha256(request),
        "config_sha256": None,
        "result_sha256": None,
        "result_bytes": None,
        "created_at": request["created_at"],
        "started_at": None,
        "updated_at": _now(),
        "finished_at": None,
        "result_available": False,
    }


def create_router_job(
    root: Path | str,
    *,
    job_root: Path | str | None = None,
    max_docs: int = 500,
    budget_ms: int = 0,
    use_cache: bool = True,
    executor: str = "process",
) -> dict[str, Any]:
    """Create local durable state for a complete router build without spawning it."""
    root_path = Path(root).resolve()
    if max_docs < 0:
        raise RouterJobError("max_docs must be non-negative")
    if budget_ms < 0:
        raise RouterJobError("budget_ms must be non-negative")
    if executor not in {"thread", "process"}:
        raise RouterJobError("executor must be 'thread' or 'process'")
    job_id = str(uuid.uuid4())
    job_dir = _job_root(job_root) / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    created = _now()
    request = {
        "schema": _REQUEST_SCHEMA,
        "job_id": job_id,
        "tool_version": __version__,
        "source_version": __version__,
        "root": str(root_path),
        "root_sha256_prefix": _root_hash(root_path),
        "max_docs": int(max_docs),
        "budget_ms": int(budget_ms),
        "use_cache": bool(use_cache),
        "executor": executor,
        "created_at": created,
    }
    _atomic_write_json(job_dir / _REQUEST_FILE, request)
    status = _base_status(job_id, request, attempt=1)
    _write_status(job_dir, status)
    receipt = dict(status)
    receipt["job_dir"] = str(job_dir)
    return receipt


def _spawn_worker(job_dir: Path, run_token: str) -> subprocess.Popen:
    args = [sys.executable, "-m", "index_graph.router_jobs", "_worker", str(job_dir), run_token]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    stdout_path = job_dir / "worker.stdout.log"
    stderr_path = job_dir / "worker.stderr.log"
    stdout = stdout_path.open("ab")
    stderr = stderr_path.open("ab")
    try:
        return subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            cwd=str(Path.cwd()),
            close_fds=True,
            creationflags=flags,
        )
    finally:
        stdout.close()
        stderr.close()


def start_router_job(
    root: Path | str,
    *,
    job_root: Path | str | None = None,
    max_docs: int = 500,
    budget_ms: int = 0,
    use_cache: bool = True,
    executor: str = "process",
) -> dict[str, Any]:
    """Start a router job and return a durable running receipt quickly."""
    receipt = create_router_job(
        root,
        job_root=job_root,
        max_docs=max_docs,
        budget_ms=budget_ms,
        use_cache=use_cache,
        executor=executor,
    )
    job_dir = Path(receipt["job_dir"])
    run_token = uuid.uuid4().hex
    with _state_lock(job_dir):
        status = _read_status_file_unlocked(job_dir)
        status["run_token"] = run_token
        status["phase"] = "starting"
        status["started_at"] = _now()
        status["worker_started_epoch"] = None
        _write_status_unlocked(job_dir, status)
    try:
        proc = _spawn_worker(job_dir, run_token)
    except OSError as exc:
        with _state_lock(job_dir):
            status = _read_status_file_unlocked(job_dir)
            status["status"] = "failed"
            status["phase"] = "failed"
            status["error_type"] = type(exc).__name__
            status["message"] = _safe_error_message(exc)
            status["result_available"] = False
            status["finished_at"] = _now()
            written = _write_status_unlocked(job_dir, status)
        written["job_dir"] = str(job_dir)
        return written
    with _state_lock(job_dir):
        current = _read_status_file_unlocked(job_dir)
        if current.get("run_token") != run_token or _is_terminal(current):
            current["job_dir"] = str(job_dir)
            return current
        if current.get("phase") != "starting":
            current["job_dir"] = str(job_dir)
            return current
        status = current
        status["pid"] = proc.pid
        status["phase"] = "started"
        status["worker_started_epoch"] = time.time()
        written = _write_status_unlocked(job_dir, status)
    written["job_dir"] = str(job_dir)
    return written


def _pid_running(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _recover_running_status(job_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    if status.get("status") not in {"running", "cancellation_requested"}:
        if status.get("status") == "complete" and not (job_dir / _RESULT_FILE).is_file():
            return _fail_status(
                job_dir,
                status,
                error_type="MissingResult",
                message="router job marked complete but result is missing",
            )
        return status
    if status.get("run_token") is None:
        return status
    if _active_worker(status, job_dir):
        return status
    if _recent_worker_start(status):
        return status
    if (job_dir / _RESULT_FILE).is_file():
        status = _fail_status(
            job_dir,
            status,
            error_type="UnsealedResult",
            message="router job worker exited with an unsealed result",
        )
    elif status.get("status") == "cancellation_requested":
        status = _fail_status(
            job_dir,
            status,
            error_type="WorkerInterrupted",
            message="router job worker stopped before acknowledging cancellation",
        )
    else:
        status = _fail_status(
            job_dir,
            status,
            error_type="WorkerInterrupted",
            message="router job worker lock is no longer active",
        )
    return status


def read_router_job_status(job_id: str, *, job_root: Path | str | None = None) -> dict[str, Any]:
    job_dir = _job_dir(job_id, job_root)
    with _state_lock(job_dir):
        status = _recover_running_status(job_dir, _read_status_file_unlocked(job_dir))
    receipt = dict(status)
    receipt["job_dir"] = str(job_dir)
    return receipt


def read_router_job_result(job_id: str, *, job_root: Path | str | None = None) -> dict[str, Any]:
    status = read_router_job_status(job_id, job_root=job_root)
    job_dir = Path(status["job_dir"])
    if status.get("status") != "complete":
        return {
            "schema": _RESULT_SCHEMA,
            "job_id": status["job_id"],
            "status": status.get("status"),
            "phase": status.get("phase"),
            "result_available": False,
            "status_receipt": status,
        }
    with _state_lock(job_dir):
        status = _read_status_file_unlocked(job_dir)
        if status.get("status") != "complete":
            receipt = dict(status)
            receipt["job_dir"] = str(job_dir)
            return {
                "schema": _RESULT_SCHEMA,
                "job_id": status["job_id"],
                "status": status.get("status"),
                "phase": status.get("phase"),
                "result_available": False,
                "status_receipt": receipt,
            }

        def failed_result(error_type: str, message: str) -> dict[str, Any]:
            failed = _fail_status(job_dir, status, error_type=error_type, message=message)
            receipt = dict(failed)
            receipt["job_dir"] = str(job_dir)
            return {
                "schema": _RESULT_SCHEMA,
                "job_id": status["job_id"],
                "status": "failed",
                "phase": "failed",
                "error_type": error_type,
                "result_available": False,
                "status_receipt": receipt,
            }

        try:
            request = _read_request(job_dir)
        except RouterJobError as exc:
            return failed_result("RequestSealInvalid", _safe_error_message(exc))
        expected_request_hash = status.get("request_sha256")
        if not isinstance(expected_request_hash, str) or _request_sha256(request) != expected_request_hash:
            return failed_result(
                "RequestSealInvalid",
                "router job request seal does not match complete status receipt",
            )
        try:
            content = _read_regular_result_text(job_dir)
        except FileNotFoundError:
            return failed_result("MissingResult", "router job result is missing")
        except RouterJobError as exc:
            return failed_result("UnsafeResult", _safe_error_message(exc))
        actual_hash = _sha256_text(content)
        expected_hash = status.get("result_sha256")
        if not isinstance(expected_hash, str) or actual_hash != expected_hash:
            return failed_result(
                "CorruptResult",
                "router job result hash does not match complete status receipt",
            )
        receipt = dict(status)
        receipt["job_dir"] = str(job_dir)
    return {
        "schema": _RESULT_SCHEMA,
        "job_id": status["job_id"],
        "status": "complete",
        "phase": "complete",
        "result_available": True,
        "result_sha256": actual_hash,
        "request_sha256": status.get("request_sha256"),
        "config_sha256": status.get("config_sha256"),
        "content": content,
        "status_receipt": receipt,
    }


def cancel_router_job(
    job_id: str,
    *,
    job_root: Path | str | None = None,
    terminate: bool = False,
) -> dict[str, Any]:
    job_dir = _job_dir(job_id, job_root)
    with _state_lock(job_dir):
        observed = _read_status_file_unlocked(job_dir)
        marker = {
            "schema": _CANCEL_SCHEMA,
            "job_id": job_dir.name,
            "run_token": observed.get("run_token"),
            "attempt": observed.get("attempt"),
            "requested_at": _now(),
        }
        _atomic_write_json(job_dir / _CANCEL_FILE, marker)
        status = _read_status_file_unlocked(job_dir)
        if status.get("status") == "complete":
            status["message"] = "router job was already complete when cancellation was requested"
            status["result_available"] = (job_dir / _RESULT_FILE).is_file()
        elif _is_terminal(status):
            status["message"] = "router job was already terminal when cancellation was requested"
            status["result_available"] = False
        elif status.get("run_token") != observed.get("run_token") or status.get("attempt") != observed.get("attempt"):
            status["message"] = "router job changed attempts before cancellation could be applied"
            status["result_available"] = False
        else:
            status["status"] = "cancellation_requested"
            status["cancel_requested_at"] = marker["requested_at"]
            status["result_available"] = False
            status["message"] = "router job cancellation requested"
        if terminate:
            status["termination_supported"] = False
            status["message"] = (
                "router job cancellation requested; hard termination was not attempted "
                "because durable jobs require an owned worker handle, not PID-only identity"
            )
        written = _write_status_unlocked(job_dir, status)
    written["job_dir"] = str(job_dir)
    return written


def resume_router_job(job_id: str, *, job_root: Path | str | None = None) -> dict[str, Any]:
    job_dir = _job_dir(job_id, job_root)
    with _state_lock(job_dir):
        status = _recover_running_status(job_dir, _read_status_file_unlocked(job_dir))
        if status.get("status") == "complete":
            status = dict(status)
            status["job_dir"] = str(job_dir)
            return status
        if status.get("status") in {"running", "cancellation_requested"} and (
            _active_worker(status, job_dir) or _recent_worker_start(status)
        ):
            status = dict(status)
            status["job_dir"] = str(job_dir)
            return status
        request = _read_request(job_dir)
        try:
            (job_dir / _CANCEL_FILE).unlink()
        except FileNotFoundError:
            pass
        next_status = _base_status(job_dir.name, request, attempt=int(status.get("attempt") or 1) + 1)
        next_status["phase"] = "restarting"
        next_status["started_at"] = _now()
        run_token = uuid.uuid4().hex
        next_status["run_token"] = run_token
        next_status["config_sha256"] = _config_sha256(Path(request["root"]).resolve())
        _write_status_unlocked(job_dir, next_status)
        try:
            proc = _spawn_worker(job_dir, run_token)
        except OSError as exc:
            next_status["status"] = "failed"
            next_status["phase"] = "failed"
            next_status["error_type"] = type(exc).__name__
            next_status["message"] = _safe_error_message(exc)
            next_status["result_available"] = False
            next_status["finished_at"] = _now()
            written = _write_status_unlocked(job_dir, next_status)
            written["job_dir"] = str(job_dir)
            return written
        current = _read_status_file_unlocked(job_dir)
        if current.get("run_token") != run_token or _is_terminal(current):
            current["job_dir"] = str(job_dir)
            return current
        if current.get("phase") != "restarting":
            current["job_dir"] = str(job_dir)
            return current
        next_status = dict(current)
        next_status["pid"] = proc.pid
        next_status["phase"] = "started"
        next_status["worker_started_epoch"] = time.time()
        written = _write_status_unlocked(job_dir, next_status)
    written["job_dir"] = str(job_dir)
    return written


def _safe_error_message(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    return " ".join(text.split())[:500]


def run_router_job_worker(job_dir: Path | str, run_token: str | None = None) -> int:
    """Run one router job in this process. Public for tests and subprocess entry."""
    job_dir = Path(job_dir).resolve()
    request = _read_request(job_dir)
    status = _read_status_file(job_dir)
    run_token = run_token or status.get("run_token") or uuid.uuid4().hex
    if not isinstance(run_token, str) or not run_token:
        run_token = uuid.uuid4().hex
    if status.get("run_token") and status.get("run_token") != run_token:
        _append_event(
            job_dir,
            {
                "phase": "failed",
                "error_type": "RouterJobLostOwnership",
                "message": "worker token does not match current job status",
            },
        )
        return 1
    started = perf_counter()
    started_epoch = time.time()
    stop_heartbeat: threading.Event | None = None
    lease_lock: BinaryIO | None = None

    def update(**fields: Any) -> dict[str, Any]:
        nonlocal status
        with _state_lock(job_dir):
            current = _read_status_file_unlocked(job_dir)
            if current.get("run_token") and current.get("run_token") != run_token:
                raise RouterJobLostOwnership("worker no longer owns this router job attempt")
            if current.get("status") in {"complete", "failed", "cancelled"} and fields.get("status") not in {
                "complete",
                "failed",
                "cancelled",
            }:
                raise RouterJobLostOwnership("worker cannot overwrite terminal router job status")
            if current.get("status") == "cancellation_requested" and fields.get("status") == "running":
                raise RouterJobCancelled("router job cancellation requested")
            if fields.get("status") == "running" and _cancel_requested(job_dir, run_token):
                raise RouterJobCancelled("router job cancellation requested")
            status = {
                **current,
                **fields,
                "run_token": run_token,
                "elapsed_ms": int((perf_counter() - started) * 1000),
            }
            return _write_status_unlocked(job_dir, status)

    def progress(event: GraphProgress) -> None:
        payload = asdict(event)
        _append_event(job_dir, payload)
        update(
            status="running",
            phase=event.phase,
            completed_repos=event.completed_repos,
            total_repos=event.total_repos,
        )
        if _cancel_requested(job_dir, run_token):
            raise RouterJobCancelled("router job cancellation requested")

    try:
        lease_lock = _acquire_lease(job_dir, run_token)
        stop_heartbeat, _thread = _start_heartbeat(job_dir, run_token, started_epoch=started_epoch)
        update(
            status="running",
            phase=status.get("phase") if status.get("phase") in {"starting", "restarting"} else "started",
            pid=os.getpid(),
            worker_started_epoch=started_epoch,
            started_at=status.get("started_at") or _now(),
            request_sha256=_request_sha256(request),
            config_sha256=None,
            result_sha256=None,
            result_bytes=None,
            result_available=False,
        )
        if _cancel_requested(job_dir, run_token):
            raise RouterJobCancelled("router job cancellation requested")
        root = Path(request["root"]).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"root not found: {root}")
        update(status="running", phase="discovering", config_sha256=_config_sha256(root))
        from .cli_handlers._common import rel_to_root, repo_paths
        from .knowledge.atlas import build_router_pack
        from .knowledge.docs import discover_router_docs
        from .router import render_router

        paths = repo_paths(root, budget_ms=int(request.get("budget_ms", 0)))
        if _cancel_requested(job_dir, run_token):
            raise RouterJobCancelled("router job cancellation requested")
        update(status="running", phase="building", completed_repos=0, total_repos=len(paths))
        repo_dirs = {name: rel_to_root(root, path) for name, path in paths.items()}
        graph = build_graph(
            paths,
            executor=str(request.get("executor") or "process"),
            use_cache=bool(request.get("use_cache", True)),
            on_progress=progress,
        )
        if _cancel_requested(job_dir, run_token):
            raise RouterJobCancelled("router job cancellation requested")
        update(status="running", phase="rendering", completed_repos=len(paths), total_repos=len(paths))
        pack = build_router_pack(graph, discover_router_docs(root), repo_dirs)
        text = render_router(pack, max_docs=max(0, int(request.get("max_docs", 500))))
        result_sha256 = _sha256_text(text)
        attempt_result = job_dir / f"router.{run_token}.md"
        _atomic_write_text(attempt_result, text)
        try:
            with _state_lock(job_dir):
                current = _read_status_file_unlocked(job_dir)
                if current.get("run_token") != run_token:
                    raise RouterJobLostOwnership("worker no longer owns this router job attempt")
                if current.get("status") in {"complete", "failed", "cancelled"}:
                    raise RouterJobLostOwnership("worker cannot overwrite terminal router job status")
                if current.get("status") == "cancellation_requested" or _cancel_requested(job_dir, run_token):
                    raise RouterJobCancelled("router job cancellation requested")
                if _result_file_is_unsafe(job_dir / _RESULT_FILE):
                    raise RouterJobError("router job result path is unsafe")
                attempt_result.replace(job_dir / _RESULT_FILE)
                status = {
                    **current,
                    "status": "complete",
                    "phase": "complete",
                    "completed_repos": len(paths),
                    "total_repos": len(paths),
                    "result_available": True,
                    "result_path": str(job_dir / _RESULT_FILE),
                    "result_sha256": result_sha256,
                    "result_bytes": len(text.encode("utf-8", "surrogateescape")),
                    "request_sha256": _request_sha256(request),
                    "config_sha256": _config_sha256(root),
                    "finished_at": _now(),
                    "elapsed_ms": int((perf_counter() - started) * 1000),
                }
                status = _write_status_unlocked(job_dir, status)
        finally:
            try:
                attempt_result.unlink()
            except FileNotFoundError:
                pass
        _append_event(job_dir, {"phase": "complete", "completed_repos": len(paths), "total_repos": len(paths), "elapsed_ms": int((perf_counter() - started) * 1000)})
        return 0
    except RouterJobAlreadyActive as exc:
        _append_event(
            job_dir,
            {
                "phase": "failed",
                "error_type": type(exc).__name__,
                "message": _safe_error_message(exc),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        return 1
    except RouterJobLostOwnership as exc:
        _append_event(
            job_dir,
            {
                "phase": "failed",
                "error_type": type(exc).__name__,
                "message": _safe_error_message(exc),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        return 1
    except RouterJobCancelled as exc:
        update(
            status="cancelled",
            phase="cancelled",
            result_available=False,
            error_type=type(exc).__name__,
            message=_safe_error_message(exc),
            finished_at=_now(),
        )
        _append_event(job_dir, {"phase": "cancelled", "completed_repos": status.get("completed_repos", 0), "total_repos": status.get("total_repos"), "elapsed_ms": int((perf_counter() - started) * 1000)})
        return 2
    except BaseException as exc:
        update(
            status="failed",
            phase="failed",
            result_available=False,
            error_type=type(exc).__name__,
            message=_safe_error_message(exc),
            finished_at=_now(),
        )
        _append_event(job_dir, {"phase": "failed", "completed_repos": status.get("completed_repos", 0), "total_repos": status.get("total_repos"), "elapsed_ms": int((perf_counter() - started) * 1000)})
        return 1
    finally:
        if stop_heartbeat is not None:
            stop_heartbeat.set()
        _release_lease(job_dir, run_token, lease_lock)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) in {2, 3} and argv[0] == "_worker":
        return run_router_job_worker(Path(argv[1]), argv[2] if len(argv) == 3 else None)
    raise SystemExit("usage: python -m index_graph.router_jobs _worker JOB_DIR [RUN_TOKEN]")


if __name__ == "__main__":
    raise SystemExit(main())
