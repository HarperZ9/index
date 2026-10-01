"""Owned state stays an explicit launch capability, never a tool grant."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


def run_client(workspace, requests, state=None, env=None):
    entry = Path(__file__).resolve().parents[1] / "client-plugin/server/serve.py"
    command = [sys.executable, "-I", "-S", "-B", str(entry), "--workspace", str(workspace)]
    if state is not None:
        command += ["--state-directory", str(state)]
    result = subprocess.run(command, input="".join(json.dumps(r)+"\n" for r in requests),
                            capture_output=True, text=True, timeout=20, env=env, check=False)
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines()]


def call(name, **arguments):
    return {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def test_launch_owned_state_enables_cache_without_ambient_state(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    ambient = tmp_path / "ambient"
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH"}}
    env["INDEX_CACHE_DIR"] = str(ambient)
    rows = run_client(workspace, [call("index.map", root=".")], state, env)
    assert not rows[0]["result"]["isError"], rows
    assert list((state / "cache").glob("*.json"))
    assert not ambient.exists()
    assert not list(workspace.iterdir())


def test_no_launch_state_means_no_extra_tools_or_arguments(tmp_path):
    rows = run_client(tmp_path, [call("index.map", root=".", resume=True),
                                call("index.router.job.status", job_id=str(uuid.uuid4()))])
    assert all(row["result"]["isError"] for row in rows)
    assert not list(tmp_path.iterdir())


def test_state_never_grants_process_jobs_or_network(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    rows = run_client(tmp_path, [call("index.router.job.start", root="."),
                                call("index.router.job.resume", job_id=str(uuid.uuid4())),
                                call("index.map", root=".", state_directory="outside")], state)
    assert all(row["result"]["isError"] for row in rows)


def test_existing_owned_job_can_be_read_and_cooperatively_cancelled(tmp_path):
    state = tmp_path / "state"
    job_id = str(uuid.uuid4())
    job = state / "jobs" / job_id
    job.mkdir(parents=True)
    (job / "request.json").write_text(json.dumps({"schema": "index.router-job-request/v1",
        "job_id": job_id, "root": str(tmp_path)}), encoding="utf-8")
    (job / "status.json").write_text(json.dumps({"schema": "index.router-job-status/v1",
        "job_id": job_id, "status": "cancelled", "phase": "cancelled"}), encoding="utf-8")
    rows = run_client(tmp_path, [call("index.router.job.status", job_id=job_id),
        call("index.router.job.cancel", job_id=job_id)], state)
    assert all(not row["result"]["isError"] for row in rows), rows
    assert (job / "cancel.request").exists()


def test_state_job_cannot_reference_workspace_outside_grant(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    job_id = str(uuid.uuid4())
    job = state / "jobs" / job_id
    job.mkdir(parents=True)
    (job / "request.json").write_text(json.dumps({"schema": "index.router-job-request/v1",
        "job_id": job_id, "root": str(tmp_path)}), encoding="utf-8")
    rows = run_client(workspace, [call("index.router.job.cancel", job_id=job_id)], state)
    assert rows[0]["result"]["isError"]
    assert not (job / "cancel.request").exists()


def test_state_cache_is_reused_and_explicitly_bypassed(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    run_client(tmp_path, [call("index.map", root=".")], state)
    cached = next((state / "cache").glob("*.json"))
    before = cached.read_bytes()
    run_client(tmp_path, [call("index.map", root=".")], state)
    assert cached.read_bytes() == before
    run_client(tmp_path, [call("index.map", root=".", no_cache=True)], state)
    assert cached.read_bytes() == before


@pytest.mark.parametrize("argument", [{"resume": True}, {"resume": "true"}, {"no_cache": 1},
    {"resume_state": "../outside"}, {"allow_process": True}])
def test_tool_arguments_cannot_widen_state(tmp_path, argument):
    state = tmp_path / "state"
    state.mkdir()
    rows = run_client(tmp_path, [call("index.map", root=".", **argument)], state)
    assert rows[0]["result"]["isError"]
    assert not list(state.iterdir())


def test_state_rejects_hard_link_before_write(tmp_path):
    from index_graph.client_state import validate_state
    outside = tmp_path / "outside"
    outside.write_text("preserve", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    try:
        (state / "linked").hardlink_to(outside)
    except OSError:
        pytest.skip("hard links unavailable")
    with pytest.raises(ValueError, match="hard links"):
        validate_state(state)
    assert outside.read_text() == "preserve"
