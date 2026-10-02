"""Client archive provenance, no-clobber, and boundary regression tests."""
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
package = __import__("build_client_package")


def test_source_bundle_is_deterministic_and_contains_runtime_source(tmp_path):
    first = package.build(tmp_path/"one", "dev")
    second = package.build(tmp_path/"two", "dev")
    assert first[0].read_bytes() == second[0].read_bytes()
    with zipfile.ZipFile(first[0]) as archive:
        names = archive.namelist()
        assert "server/src/" + package.SPEC["pkg"] + "/client_mcp.py" in names
        assert {"plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
                ".claude-plugin/icon.png"} <= set(names)
        assert all(".." not in Path(name).parts and not Path(name).is_absolute() for name in names)
        assert json.loads(archive.read("plugin.json"))["version"] == package.version()
    with pytest.raises(ValueError, match="new directory"):
        package.build(tmp_path/"one", "dev")

def test_release_refuses_unqualified_working_source(monkeypatch):
    monkeypatch.setattr(package, "git", lambda *args: " M source.py" if args[0] == "status" else "a" * 40)
    with pytest.raises(ValueError):
        package.qualify("release")

def test_version_mismatch_stops_before_output(monkeypatch, tmp_path):
    monkeypatch.setitem(package.SPEC, "version", "999.0.0")
    with pytest.raises(ValueError, match="version mismatch"):
        package.build(tmp_path/"absent", "dev")
    assert not (tmp_path/"absent").exists()

def test_archive_rejects_symlink(tmp_path):
    target = tmp_path/"target"
    target.mkdir()
    (target/"safe.py").write_text("x = 1")
    path = tmp_path/"payload"
    path.mkdir()
    try:
        (path/"link").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(ValueError, match="link"):
        package.entries(path)

def test_ignored_credentials_never_enter_package(tmp_path):
    (tmp_path / ".env").write_text("DO_NOT_PACKAGE=synthetic", encoding="utf-8")
    with pytest.raises(ValueError, match="credential"):
        package.entries(tmp_path)

def test_native_validator_rejects_duplicate_keys():
    from check_native_client import strict_json
    with pytest.raises(ValueError, match="duplicate"):
        strict_json('{"isError":true,"isError":false}')

def test_native_validator_rejects_non_text_content():
    from check_native_client import payload_of
    with pytest.raises(ValueError):
        payload_of({"content": [{"type": "text", "text": {"pretend": "success"}}]})

def test_release_collection_rejects_ignored_payload_even_if_git_is_clean(tmp_path, monkeypatch):
    tracked = []
    for folder in ("src", "scripts", "client-plugin"):
        directory = tmp_path / folder
        directory.mkdir()
        (directory / "reviewed.py").write_text("# reviewed source", encoding="utf-8")
        tracked.append(folder + "/reviewed.py")
    (tmp_path / "src" / "ignored-private.txt").write_text("synthetic private sentinel", encoding="utf-8")
    monkeypatch.setattr(package, "ROOT", tmp_path)
    monkeypatch.setattr(package, "qualify", lambda mode: {"mode": mode, "version": "1.0.0", "commit": "a"*40})
    monkeypatch.setattr(package, "git", lambda *args: "\n".join(tracked) if args == ("ls-files",) else "")
    with pytest.raises(ValueError, match="untracked or ignored"):
        package.build(tmp_path.parent / (tmp_path.name + "-output"), "release")

def test_extracted_source_plugin_runs_without_installed_project(tmp_path):
    import subprocess
    archive = package.build(tmp_path / "build", "dev")[0]
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample.md").write_text("A synthetic source contains 14 records.", encoding="utf-8")
    (workspace / "thesis.json").write_text(json.dumps({"title": "Synthetic", "claims": [
        {"text": "14 records exist", "falsification": "a count other than 14"}]}), encoding="utf-8")
    wire = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": package.SPEC["tool"], "arguments": package.SPEC["args"]}}) + "\n"
    result = subprocess.run([sys.executable, "-I", "-S", "-B", str(extracted / "server/serve.py"),
                             "--workspace", str(workspace)], input=wire, capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)
    assert row["result"]["isError"] is False, row
    assert isinstance(row["result"]["content"][0]["text"], str)

def test_claude_manifest_carries_directory_listing_and_prompts_for_bindings():
    from client_manifest import claude_mcp, claude_plugin, manifest
    plugin_dir = ROOT / "client-plugin"
    claude = json.loads((plugin_dir / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert claude == claude_plugin(package.SPEC, package.version())
    portable = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((plugin_dir / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    for key in ("homepage", "documentationUrl", "supportUrl", "privacyPolicyUrl", "termsOfServiceUrl"):
        assert claude[key].startswith("https://")
    assert claude["repository"] == "https://github.com/HarperZ9/index"
    assert claude["displayName"] == "Index" and 5 <= len(claude["keywords"]) <= 8
    assert all(k == k.lower() for k in claude["keywords"])
    for key in ("name", "version", "license", "author", "description"):
        assert claude[key] == portable[key] == codex[key]
    for other in (portable, codex):
        assert "userConfig" not in other and "icon" not in other and "displayName" not in other
    # The Claude plugin offers the same settings and defaults as the native MCPB.
    native = manifest(package.SPEC, package.version(), "index-local.exe")["user_config"]
    assert claude["userConfig"] == native
    assert claude["userConfig"]["workspace"] == {**native["workspace"], "type": "directory", "required": True}
    assert claude["userConfig"]["state_directory"]["default"] == ""
    mcp = json.loads((plugin_dir / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp == claude_mcp()
    args = mcp["mcpServers"]["index"]["args"]
    assert [a for a in args if "${" in a] == ["${CLAUDE_PLUGIN_ROOT}/server/serve.py",
        "${user_config.workspace}", "--state-directory=${user_config.state_directory}"]
    assert "REPLACE_WITH" not in (plugin_dir / ".mcp.json").read_text(encoding="utf-8")
    assert "REPLACE_WITH_ABSOLUTE_WORKSPACE" in json.loads((plugin_dir / "mcp.json").read_text())["mcpServers"]["index"]["args"]


def test_claude_launch_arguments_parse_after_substitution(tmp_path):
    """Substituted userConfig values, including an empty state directory, start the server."""
    import subprocess
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    wire = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    names = []
    for value in ("", str(state)):
        args = [a.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT / "client-plugin"))
                 .replace("${user_config.workspace}", str(workspace))
                 .replace("${user_config.state_directory}", value)
                for a in json.loads((ROOT / "client-plugin/.mcp.json").read_text())["mcpServers"]["index"]["args"]]
        result = subprocess.run([sys.executable, *args], input=wire, capture_output=True, text=True,
                                timeout=20, check=False)
        assert result.returncode == 0, result.stderr
        names.append({t["name"] for t in json.loads(result.stdout)["result"]["tools"]})
    assert "index.symbol-definition" in names[0] and "index.router.job.status" not in names[0]
    assert "index.router.job.status" in names[1]


def test_committed_icon_is_a_square_png_the_directory_accepts():
    data = (ROOT / "client-plugin/.claude-plugin/icon.png").read_bytes()
    assert data[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10]) and data[12:16] == b"IHDR"
    width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    assert width == height and 512 <= width <= 2048 and len(data) < 2 * 1024 * 1024


def test_client_plugin_has_no_root_instruction_file():
    assert not (ROOT / "client-plugin/CLAUDE.md").exists()
