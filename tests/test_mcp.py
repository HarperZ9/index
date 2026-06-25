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
    for t in r["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"


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


def test_tools_call_error_is_flagged(tmp_path):
    r = handle_request({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                        "params": {"name": "index_verify",
                                   "arguments": {"root": str(tmp_path / "nope")}}})
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
