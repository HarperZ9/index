import json

import pytest

from index_graph import router_jobs
from index_graph.cli import main
from index_graph.mcp import handle_request


def _call(action, arguments):
    return handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": f"index.router.job.{action}",
                                      "arguments": arguments}})


@pytest.mark.parametrize("action,function", [
    ("status", "read_router_job_status"), ("result", "read_router_job_result"),
    ("cancel", "cancel_router_job"), ("resume", "resume_router_job"),
])
def test_existing_job_cli_mcp_parity_without_root(action, function, monkeypatch, capsys):
    receipt = {"job_id": "example", "status": "running", "result_available": False}
    seen = []
    def invoke(job_id):
        seen.append(job_id)
        return receipt
    monkeypatch.setattr(router_jobs, function, invoke)
    assert main(["router-job", action, "example"]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    response = _call(action, {"job_id": "example"})
    assert response["result"]["isError"] is False
    assert json.loads(response["result"]["content"][0]["text"]) == receipt
    assert seen == ["example", "example"]


def test_start_parity_and_explicit_cache_bypass(tmp_path, monkeypatch, capsys):
    seen = []
    def start(root, **kwargs):
        seen.append((root, kwargs))
        return {"status": "running", "job_id": "created"}
    monkeypatch.setattr(router_jobs, "start_router_job", start)
    assert main(["router-job", "start", "--root", str(tmp_path), "--max-docs", "7",
                 "--no-cache"]) == 0
    cli = json.loads(capsys.readouterr().out)
    response = _call("start", {"root": str(tmp_path), "max_docs": 7, "no_cache": True})
    assert response["result"]["isError"] is False
    assert json.loads(response["result"]["content"][0]["text"]) == cli
    assert seen[0] == seen[1]
    assert seen[0][1] == {"max_docs": 7, "budget_ms": 0, "use_cache": False}


@pytest.mark.parametrize("arguments", [
    {}, {"root": 1}, {"root": ".", "max_docs": True},
    {"root": ".", "budget_ms": 0.5}, {"root": ".", "budget_ms": -1},
    {"root": ".", "no_cache": "false"}, {"root": ".", "job_root": "elsewhere"},
])
def test_invalid_start_never_spawns(arguments, monkeypatch):
    monkeypatch.setattr(router_jobs, "start_router_job", lambda *a, **kw: pytest.fail("spawned"))
    response = _call("start", arguments)
    assert response["result"]["isError"] is True


def test_tools_advertise_recovery_without_root():
    result = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    definitions = {tool["name"]: tool for tool in result["result"]["tools"]}
    for action in ("status", "result", "cancel", "resume"):
        schema = definitions[f"index.router.job.{action}"]["inputSchema"]
        assert schema["required"] == ["job_id"]
        assert schema["additionalProperties"] is False
