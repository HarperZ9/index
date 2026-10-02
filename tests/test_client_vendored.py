"""The plugin folder must run on its own: vendored server code, size limits, isolated launch."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "client-plugin"
sys.path.insert(0, str(ROOT / "scripts"))
package = __import__("build_client_package")
SYNC = "python scripts/build_client_package.py --sync-vendored"


def _lf(data):
    return data.replace(b"\r\n", b"\n")


def test_vendored_server_code_matches_the_builder():
    expected = {k: _lf(v) for k, v in package.vendored_payload().items()}
    committed = {"server/src/" + p.relative_to(PLUGIN / "server/src").as_posix(): _lf(p.read_bytes())
                 for p in (PLUGIN / "server/src").rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}}
    missing = sorted(set(expected) - set(committed))
    extra = sorted(set(committed) - set(expected))
    changed = sorted(k for k in set(expected) & set(committed) if expected[k] != committed[k])
    assert not (missing or extra or changed), (
        f"client-plugin/server/src is out of date (missing {missing[:5]}, extra {extra[:5]}, "
        f"changed {changed[:5]}). Run: {SYNC}")


def test_builder_inputs_do_not_count_the_vendored_copy_twice():
    assert not any(k.startswith("server/src/") for k in package.plugin_entries())


def test_plugin_folder_fits_directory_limits():
    files = [p for p in PLUGIN.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert len(files) <= 512, len(files)
    # The directory's 256 KiB rule covers every file that is not an image or font.
    exempt = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    large = [(p.relative_to(PLUGIN).as_posix(), p.stat().st_size) for p in files
             if p.suffix.lower() not in exempt and p.stat().st_size >= 256 * 1024]
    assert not large, large
    assert not list(PLUGIN.rglob(".gitattributes"))


def _launch(folder, workspace, requests):
    server = json.loads((folder / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["index"]
    defaults = {"workspace": str(workspace), "state_directory": ""}
    args = [a.replace("${CLAUDE_PLUGIN_ROOT}", str(folder)) for a in server["args"]]
    for key, value in defaults.items():
        args = [a.replace("${user_config." + key + "}", value) for a in args]
    assert not any("${" in a for a in args), args
    command = [sys.executable if server["command"] == "python3" else server["command"], *args]
    env = None
    if server.get("env"):
        import os
        env = {**os.environ, **server["env"]}
    wire = "".join(json.dumps(r) + "\n" for r in requests)
    return subprocess.run(command, input=wire, capture_output=True, text=True, timeout=30, env=env, check=False)


def test_plugin_folder_alone_starts_and_lists_tools(tmp_path):
    folder = tmp_path / "plugin"
    shutil.copytree(PLUGIN, folder, ignore=shutil.ignore_patterns("__pycache__"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    result = _launch(folder, workspace, requests)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert rows[0]["result"]["serverInfo"]["name"] == "index-local"
    names = {t["name"] for t in rows[1]["result"]["tools"]}
    assert {"index.map", "index.select", "index.symbol-definition", "index.symbol-references"} <= names
    shutil.rmtree(folder / "server/src")
    result = _launch(folder, workspace, requests)
    assert result.returncode == 1 and not result.stdout
    assert result.stderr.strip() == "index: the server code is missing from the plugin folder. Reinstall the plugin."
