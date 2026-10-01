"""Meaningful client boundary regressions; no model or network calls."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from index_graph import __version__
from index_graph.client_mcp import confined, handle


def test_map_is_text_json_and_keeps_local_config_out(tmp_path):
    (tmp_path / "README.md").write_text("Synthetic repo", encoding="utf-8")
    (tmp_path / ".index.toml").write_text("invalid config that must not be loaded", encoding="utf-8")
    result = handle({"id": 8, "method": "tools/call", "params": {
        "name": "index.map", "arguments": {"root": "."}}}, tmp_path)
    assert result["result"]["isError"] is False
    data = json.loads(result["result"]["content"][0]["text"])
    assert data["absolute_paths_included"] is False
    assert data["repo_count"] == 0

def request(name, args):
    return {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": name, "arguments": args}}

def test_version_parity(tmp_path):
    result = handle({"id": 1, "method": "initialize"}, tmp_path)
    assert result["result"]["serverInfo"]["version"] == __version__

@pytest.mark.parametrize("value", ["../outside.txt", "//localhost/share", "C:/Windows/system.ini", "sample.md:secret", "NUL"])
def test_outside_or_device_path_is_rejected(tmp_path, value):
    with pytest.raises((ValueError, OSError)):
        confined(tmp_path, value)

def test_links_refused(tmp_path):
    outside = tmp_path.parent / "outside-client.txt"
    outside.write_text("private", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(ValueError):
        confined(tmp_path, str(link))

def test_ungranted_tool_refused_even_with_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GATHER_ALLOW_EXEC", "all")
    monkeypatch.setenv("GATHER_ALLOW_NETWORK", "all")
    result = handle(request("index.router.job.start", {"allow_exec": True}), tmp_path)
    assert result["result"]["isError"] is True
    assert "TOOL_NOT_GRANTED" in result["result"]["content"][0]["text"]

def test_arguments_cannot_grant_permissions(tmp_path):
    result = handle(request("index.select", {"root":".","suffixes":[".md"],"allow_exec":True}), tmp_path)
    assert result["result"]["isError"] is True

def test_missing_launch_root_exits_without_server(tmp_path):
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-I", "-S", "-B", str(root / "client-plugin/server/serve.py")]
    result = subprocess.run(command, cwd=tmp_path, input="", capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 2
    assert "--workspace" in result.stderr

def test_actual_stdio_safe_workflow(tmp_path):
    (tmp_path / "sample.md").write_text("A synthetic source contains 14 records.", encoding="utf-8")
    (tmp_path / "thesis.json").write_text(json.dumps({"title": "Synthetic",
        "claims": [{"statement": "14 records exist", "falsification": "a count other than 14"}]}), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    requests = [{"id": 1, "method": "initialize"}, request("index.select", {"root":".","suffixes":[".md"]})]
    command = [sys.executable, "-I", "-S", "-B", str(root / "client-plugin/server/serve.py"),
               "--workspace", str(tmp_path)]
    result = subprocess.run(command, cwd=tmp_path, input="".join(json.dumps(r)+"\n" for r in requests),
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 2
    assert rows[0]["result"]["serverInfo"]["version"] == __version__
    assert rows[1]["result"]["isError"] is False, rows[1]
    assert json.loads(rows[1]["result"]["content"][0]["text"])

def test_launch_boundary_blocks_processes_and_map_keeps_unknown_metadata(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='synthetic'\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    wire = json.dumps({"id": 1, "method": "tools/call", "params": {
        "name": "index.map", "arguments": {"root": "."}}}) + "\n"
    result = subprocess.run([sys.executable, "-I", "-S", "-B",
        str(root / "client-plugin/server/serve.py"), "--workspace", str(tmp_path)],
        input=wire, capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["repo_count"] == 1
    assert payload["metadata_unknown_count"] == 1
    assert payload["metadata_ok_count"] == 0

def test_process_boundary_cannot_be_disabled_by_inherited_environment(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = ("import sys,subprocess; sys.path.insert(0,sys.argv[1]); "
              "from index_graph.client_mcp import install_process_boundary; install_process_boundary(); "
              "subprocess.run([sys.executable,'-c','print(123)'])")
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script, str(root/"src")],
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode != 0
    assert "PermissionError" in result.stderr
    assert "does not grant processes or network" in result.stderr
    assert not result.stdout
