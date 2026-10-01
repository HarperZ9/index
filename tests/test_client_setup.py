"""Exercise MCPB configuration substitution as literal process arguments."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def launch(workspace, state=None):
    from build_client_package import SPEC, version
    from client_manifest import manifest
    config = manifest(SPEC, version(), "index-local.exe")
    values = {key: field.get("default", "") for key, field in config["user_config"].items()}
    values["workspace"] = str(workspace)
    if state is not None:
        values["state_directory"] = state
    args = config["server"]["mcp_config"]["args"]
    for key, value in values.items():
        args = [arg.replace("${user_config." + key + "}", value) for arg in args]
    assert args == ["--workspace", str(workspace), "--state-directory", values["state_directory"]]
    wire = json.dumps({"id": 1, "method": "tools/call", "params": {
        "name": "index.map", "arguments": {"root": "."}}}) + "\n"
    result = subprocess.run([sys.executable, "-I", "-S", "-B",
        str(ROOT / "client-plugin/server/serve.py"), *args], input=wire,
        capture_output=True, text=True, timeout=20, check=False)
    return result


def test_default_mcpb_setup_connects_without_state(tmp_path):
    result = launch(tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["result"]["isError"] is False
    assert not list(tmp_path.iterdir())


def test_enabled_mcpb_setup_writes_only_selected_state(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state with spaces"
    state.mkdir()
    result = launch(workspace, str(state))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["result"]["isError"] is False
    assert list((state / "cache").glob("*.json"))
    assert not list(workspace.iterdir())


@pytest.mark.parametrize("state", ["relative", "../escape", "--allow-process", "${user_config.state_directory}"])
def test_malformed_setup_does_not_start_server(tmp_path, state):
    result = launch(tmp_path, state)
    assert result.returncode != 0
    assert not result.stdout
    assert not list(tmp_path.iterdir())


def test_nonexistent_setup_directory_is_not_created(tmp_path):
    result = launch(tmp_path, str(tmp_path / "missing"))
    assert result.returncode != 0
    assert not result.stdout
    assert not list(tmp_path.iterdir())
