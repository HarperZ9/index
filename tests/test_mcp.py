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
    assert {"index.map", "index.context", "index.context.envelope", "index.status", "index.doctor"} <= names
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


def test_mcp_workspace_tool_uses_cache_for_repeated_call(tmp_path, monkeypatch):
    monkeypatch.setenv("INDEX_MCP_CACHE_TTL_SECONDS", "60")
    import index_graph.mcp as mcp_mod
    import index_graph.graph.build as build_mod

    mcp_mod._CACHE.clear()
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    calls = {"count": 0}
    real = build_mod.build_graph

    def counted(*args, **kwargs):
        calls["count"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(build_mod, "build_graph", counted)
    for _ in range(2):
        r = handle_request({"jsonrpc": "2.0", "id": 16, "method": "tools/call",
                            "params": {"name": "index_graph",
                                       "arguments": {"root": str(tmp_path)}}})
        assert r["result"]["isError"] is False
        rec = json.loads(r["result"]["content"][0]["text"])
        assert rec["repos"][0]["name"] == "solo"
    assert calls["count"] == 1


def test_mcp_workspace_tool_ignores_non_utf8_filesystem_cache(tmp_path, monkeypatch):
    import index_graph.mcp as mcp_mod

    monkeypatch.setenv("INDEX_MCP_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("INDEX_MCP_CACHE_DIR", str(tmp_path / "cache"))
    mcp_mod._CACHE.clear()
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    root = tmp_path.resolve()
    key = mcp_mod._cache_key("index_graph", root, {"root": str(tmp_path)})
    path = mcp_mod._cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'{"schema":"index.mcp-cache-entry/v1","text":"bad \xda"}')

    r = handle_request({"jsonrpc": "2.0", "id": 18, "method": "tools/call",
                        "params": {"name": "index_graph",
                                   "arguments": {"root": str(tmp_path)}}})
    assert r["result"]["isError"] is False
    rec = json.loads(r["result"]["content"][0]["text"])
    assert rec["repos"][0]["name"] == "solo"


def test_mcp_router_honors_max_docs(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    for index in range(3):
        (tmp_path / "solo" / f"doc{index}.md").write_text(f"# Doc {index}\n", encoding="utf-8")
    r = handle_request({"jsonrpc": "2.0", "id": 17, "method": "tools/call",
                        "params": {"name": "index_router",
                                   "arguments": {"root": str(tmp_path), "max_docs": 1}}})
    assert r["result"]["isError"] is False
    text = r["result"]["content"][0]["text"]
    assert "doc edge(s) omitted" in text


def test_context_envelope_tool_returns_budgeted_packet(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    r = handle_request({"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                        "params": {"name": "index.context.envelope",
                                   "arguments": {"root": str(tmp_path), "budget": 80}}})
    assert r["result"]["isError"] is False
    rec = json.loads(r["result"]["content"][0]["text"])
    assert rec["schema"] == "project-telos.context-envelope/v1"
    assert rec["budget"]["token_budget"] == 80
    assert rec["retained"][0]["name"] == "solo"


def test_select_tool_reconciles_and_missing_root_is_a_receipt(tmp_path):
    (tmp_path / "README.md").write_text("# top\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    r = handle_request({"jsonrpc": "2.0", "id": 14, "method": "tools/call",
                        "params": {"name": "index.select",
                                   "arguments": {"root": str(tmp_path),
                                                 "suffixes": [".md"]}}})
    assert r["result"]["isError"] is False
    rec = json.loads(r["result"]["content"][0]["text"])
    assert rec["selection"]["selected"] == ["README.md"]
    assert rec["reconciliation"]["verdict"] == "MATCH"
    # a missing root is a not-found receipt, not a protocol error
    missing = handle_request({"jsonrpc": "2.0", "id": 15, "method": "tools/call",
                              "params": {"name": "index.select",
                                         "arguments": {"root": str(tmp_path / "nope")}}})
    assert missing["result"]["isError"] is False
    body = json.loads(missing["result"]["content"][0]["text"])
    assert [x["reason_code"] for x in body["selection"]["rejected"]] == ["not-found"]


def test_tools_call_error_is_flagged(tmp_path):
    r = handle_request({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                        "params": {"name": "index_verify",
                                   "arguments": {"root": str(tmp_path / "nope")}}})
    assert r["result"]["isError"] is True
    payload = json.loads(r["result"]["content"][0]["text"])
    assert payload["schema"] == "index.mcp-tool-error/v1"
    assert payload["status"] == "UNVERIFIABLE"


def test_unknown_tool_is_invalid_params(tmp_path):
    r = handle_request({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "nope", "arguments": {"root": str(tmp_path)}}})
    assert r["error"]["code"] == -32602


def test_missing_root_is_clear_error():
    r = handle_request({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                        "params": {"name": "index_graph", "arguments": {}}})
    assert r["result"]["isError"] is True
    payload = json.loads(r["result"]["content"][0]["text"])
    assert payload["schema"] == "index.mcp-tool-error/v1"
    assert "root" in payload["message"]


def test_mcp_tool_converts_system_exit_to_typed_error(tmp_path, monkeypatch):
    import index_graph.mcp as mcp_mod

    def boom(_root):
        raise SystemExit("bad config")

    monkeypatch.setattr(mcp_mod, "_repo_paths", boom)
    r = handle_request({"jsonrpc": "2.0", "id": 19, "method": "tools/call",
                        "params": {"name": "index_graph", "arguments": {"root": str(tmp_path)}}})

    assert r["result"]["isError"] is True
    payload = json.loads(r["result"]["content"][0]["text"])
    assert payload["schema"] == "index.mcp-tool-error/v1"
    assert payload["error_type"] == "SystemExit"
    assert payload["status"] == "UNVERIFIABLE"


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


def _stdio_frame(message):
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def _parse_stdio_frames(raw):
    frames = []
    offset = 0
    while offset < len(raw):
        header_end = raw.index("\r\n\r\n", offset)
        header = raw[offset:header_end]
        length = int(header.split(":", 1)[1].strip())
        body_start = header_end + 4
        body = raw[body_start:body_start + length]
        frames.append(json.loads(body))
        offset = body_start + length
    return frames


def test_serve_framed_stdio_roundtrip():
    inp = io.BytesIO(
        _stdio_frame({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        + _stdio_frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    )
    out = io.StringIO()
    serve(inp, out)
    frames = _parse_stdio_frames(out.getvalue())
    assert frames[0]["result"]["serverInfo"]["name"] == "index-graph"
    assert "tools" in frames[1]["result"]
