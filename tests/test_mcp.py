import io
import json

from index_graph.mcp import handle_request, serve


def test_initialize():
    r = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r["result"]["serverInfo"]["name"] == "index-graph"
    assert r["result"]["protocolVersion"]


def test_tools_list_has_core_tools():
    r = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in r["result"]["tools"]}
    assert {"index_graph", "index_focus", "index_verify", "index_router", "index_internals"} <= names
    assert {"index.map", "index.context", "index.status", "index.doctor"} <= names
    for t in r["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"


def test_status_tool_returns_cli_action_envelope_without_root():
    r = handle_request({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                        "params": {"name": "index.status", "arguments": {}}})
    assert r["result"]["isError"] is False
    payload = json.loads(r["result"]["content"][0]["text"])
    assert payload["schema"] == "project-telos.flagship-action/v1"
    assert payload["tool"] == "index"
    assert payload["command"] == "status"
    assert payload["native"]["role"] == "structure-context"


def test_doctor_tool_returns_cli_action_envelope_without_root():
    r = handle_request({"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                        "params": {"name": "index.doctor", "arguments": {}}})
    assert r["result"]["isError"] is False
    payload = json.loads(r["result"]["content"][0]["text"])
    assert payload["schema"] == "project-telos.flagship-action/v1"
    assert payload["tool"] == "index"
    assert payload["command"] == "doctor"
    assert payload["native"]["checks"][0]["status"] == "MATCH"

def test_notification_returns_none():
    assert handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_is_jsonrpc_error():
    r = handle_request({"jsonrpc": "2.0", "id": 9, "method": "bogus"})
    assert r["error"]["code"] == -32601


def test_tools_call_verify(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    r = handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "index_verify",
                                   "arguments": {"root": str(tmp_path), "exists": "solo"}}})
    assert r["result"]["isError"] is False
    rec = json.loads(r["result"]["content"][0]["text"])
    assert rec["verdict"] == "MATCH"


def test_catalog_map_alias_returns_inventory(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    r = handle_request({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                        "params": {"name": "index.map", "arguments": {"root": str(tmp_path)}}})
    assert r["result"]["isError"] is False
    rec = json.loads(r["result"]["content"][0]["text"])
    assert rec["repo_count"] == 1
    assert rec["repositories"][0]["path"] == "solo"


def test_catalog_context_alias_returns_graph_pack(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    r = handle_request({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                        "params": {"name": "index.context", "arguments": {"root": str(tmp_path)}}})
    assert r["result"]["isError"] is False
    rec = json.loads(r["result"]["content"][0]["text"])
    assert rec["repos"][0]["name"] == "solo"


def test_tools_call_error_is_flagged(tmp_path):
    r = handle_request({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                        "params": {"name": "index_verify",
                                   "arguments": {"root": str(tmp_path / "nope")}}})
    assert r["result"]["isError"] is True


def test_unknown_tool_is_invalid_params(tmp_path):
    r = handle_request({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "nope", "arguments": {"root": str(tmp_path)}}})
    assert r["error"]["code"] == -32602


def test_missing_root_is_clear_error():
    r = handle_request({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                        "params": {"name": "index_graph", "arguments": {}}})
    assert r["result"]["isError"] is True
    assert "root" in r["result"]["content"][0]["text"]


def test_depends_without_arrow_is_error(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    r = handle_request({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                        "params": {"name": "index_verify",
                                   "arguments": {"root": str(tmp_path), "depends": "noarrow"}}})
    assert r["result"]["isError"] is True


def test_serve_roundtrip():
    inp = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
                      '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
                      '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n')
    out = io.StringIO()
    serve(inp, out)
    lines = [ln for ln in out.getvalue().splitlines() if ln]
    # initialize and tools/list respond; the notification does not
    assert len(lines) == 2
    assert json.loads(lines[0])["result"]["serverInfo"]["name"] == "index-graph"
    assert "tools" in json.loads(lines[1])["result"]
