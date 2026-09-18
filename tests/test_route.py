import json

from index_graph.cli import main
from index_graph.mcp import handle_request

from test_bench import _repo


def _mcp_route(arguments):
    return handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "index.route", "arguments": arguments},
    })


def _assert_reconciles(payload):
    counts = payload["reconciliation"]
    assert (
        counts["candidate_count"]
        == counts["selected_count"] + counts["rejected_count"] + counts["omitted_count"]
    )


def _json_blob(payload):
    return json.dumps(payload, sort_keys=True).replace("\\\\", "/")


def _assert_private_path_absent(payload, *paths_or_fragments):
    blob = _json_blob(payload)
    for value in paths_or_fragments:
        assert str(value).replace("\\", "/") not in blob


def _assert_outside_locator(rejection):
    assert rejection["path"].startswith("outside-root:")
    assert rejection["path_kind"] == "outside-root"
    assert len(rejection["path_sha256"]) == 64


def test_route_explicit_path_builds_envelope_without_workspace_discovery(tmp_path, monkeypatch, capsys):
    _repo(tmp_path / "app", "app", dep="lib", body_files=1)
    _repo(tmp_path / "lib", "lib", body_files=1)
    _repo(tmp_path / "unused", "unused", body_files=1)

    import index_graph.scan as scan

    def fail_global_discovery(*_args, **_kwargs):
        raise AssertionError("route should not discover unrelated workspace repositories")

    monkeypatch.setattr(scan, "discover_repos", fail_global_discovery)

    assert main([
        "route", "--root", str(tmp_path), "--path", "app", "--budget", "900", "--json"
    ]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "index.route/v1"
    assert payload["status"] == "MATCH"
    assert payload["failure_codes"] == []
    assert payload["selection"]["selected"] == [{"key": "app", "path": "app"}]
    assert payload["selection"]["rejected"] == []
    assert payload["reconciliation"] == {
        "candidate_count": 1,
        "selected_count": 1,
        "rejected_count": 0,
        "omitted_count": 0,
    }
    _assert_reconciles(payload)
    assert [item["name"] for item in payload["envelope"]["retained"]] == ["app"]
    _assert_private_path_absent(payload, tmp_path)


def test_route_rejects_escaping_path_with_typed_receipt(tmp_path, capsys):
    _repo(tmp_path / "app", "app", body_files=1)

    assert main([
        "route", "--root", str(tmp_path), "--path", "..", "--json"
    ]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "index.route/v1"
    assert payload["status"] == "UNVERIFIABLE"
    assert payload["failure_codes"] == ["no_selected_repositories"]
    assert payload["selection"]["selected"] == []
    rejection = payload["selection"]["rejected"][0]
    assert rejection["reason_code"] == "outside-root"
    assert rejection["rule_ref"] == "route.explicit_path.contained"
    _assert_outside_locator(rejection)
    _assert_reconciles(payload)
    assert payload["envelope"] is None


def test_route_duplicate_explicit_path_is_accounted_for(tmp_path, capsys):
    _repo(tmp_path / "app", "app", body_files=1)

    assert main([
        "route", "--root", str(tmp_path), "--path", "app", "--path", "app", "--json"
    ]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "index.route/v1"
    assert payload["status"] == "PARTIAL"
    assert payload["failure_codes"] == ["candidate_rejected"]
    assert payload["selection"]["selected"] == [{"key": "app", "path": "app"}]
    assert payload["selection"]["rejected"] == [
        {"path": "app", "reason_code": "duplicate-path", "rule_ref": "route.explicit_path.unique"}
    ]
    assert payload["reconciliation"] == {
        "candidate_count": 2,
        "selected_count": 1,
        "rejected_count": 1,
        "omitted_count": 0,
    }
    _assert_reconciles(payload)


def test_route_absolute_outside_path_is_sanitized_in_cli_and_mcp(tmp_path, capsys):
    outside = tmp_path.parent / "private-sensitive-route-target" / "not-a-repo"

    assert main(["route", "--root", str(tmp_path), "--path", str(outside), "--json"]) == 2
    cli_payload = json.loads(capsys.readouterr().out)
    cli_rejection = cli_payload["selection"]["rejected"][0]
    _assert_outside_locator(cli_rejection)
    assert cli_rejection["was_absolute"] is True
    _assert_private_path_absent(cli_payload, tmp_path, outside, "private-sensitive-route-target")

    response = _mcp_route({"root": str(tmp_path), "paths": [str(outside)]})
    assert response["result"]["isError"] is False
    mcp_payload = json.loads(response["result"]["content"][0]["text"])
    _assert_outside_locator(mcp_payload["selection"]["rejected"][0])
    _assert_private_path_absent(mcp_payload, tmp_path, outside, "private-sensitive-route-target")


def test_route_missing_absolute_path_under_root_is_root_relative(tmp_path, capsys):
    missing = tmp_path / "missing-repo"

    assert main(["route", "--root", str(tmp_path), "--path", str(missing), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["selection"]["rejected"] == [
        {"path": "missing-repo", "reason_code": "not-found", "rule_ref": "route.explicit_path.exists"}
    ]
    _assert_private_path_absent(payload, tmp_path, missing)


def test_route_mixed_selected_and_outside_absolute_path_stays_portable(tmp_path, capsys):
    _repo(tmp_path / "app", "app", body_files=1)
    outside = tmp_path.parent / "private-mixed-route-target"

    assert main([
        "route", "--root", str(tmp_path), "--path", "app", "--path", str(outside), "--json"
    ]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "PARTIAL"
    assert payload["failure_codes"] == ["candidate_rejected"]
    _assert_outside_locator(payload["selection"]["rejected"][0])
    _assert_reconciles(payload)
    _assert_private_path_absent(payload, tmp_path, outside, "private-mixed-route-target")


def test_route_duplicate_absolute_path_is_rejected_without_absolute_echo(tmp_path, capsys):
    app = _repo(tmp_path / "app", "app", body_files=1)

    assert main([
        "route", "--root", str(tmp_path), "--path", str(app), "--path", str(app), "--json"
    ]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["selection"]["selected"] == [{"key": "app", "path": "app"}]
    assert payload["selection"]["rejected"] == [
        {"path": "app", "reason_code": "duplicate-path", "rule_ref": "route.explicit_path.unique"}
    ]
    _assert_reconciles(payload)
    _assert_private_path_absent(payload, tmp_path, app)


def test_route_tiny_budget_is_unverifiable_when_envelope_overflows(tmp_path, capsys):
    _repo(tmp_path / "app", "app", body_files=1)

    assert main([
        "route", "--root", str(tmp_path), "--path", "app", "--budget", "1", "--json"
    ]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "UNVERIFIABLE"
    assert payload["failure_codes"] == ["envelope_unverifiable"]
    assert payload["reconciliation"] == {
        "candidate_count": 1,
        "selected_count": 1,
        "rejected_count": 0,
        "omitted_count": 0,
    }
    _assert_reconciles(payload)
    assert payload["envelope"]["verification_verdict"] == "UNVERIFIABLE"
    assert "budget_overflow" in payload["envelope"]["failure_codes"]


def test_route_cli_and_mcp_payloads_match_for_explicit_path(tmp_path, capsys):
    _repo(tmp_path / "app", "app", body_files=1)

    assert main([
        "route", "--root", str(tmp_path), "--path", "app", "--budget", "900", "--json"
    ]) == 0
    cli_payload = json.loads(capsys.readouterr().out)

    response = _mcp_route({"root": str(tmp_path), "paths": ["app"], "budget": 900})

    assert response["result"]["isError"] is False
    assert json.loads(response["result"]["content"][0]["text"]) == cli_payload


def test_route_mcp_lists_explicit_path_tool():
    result = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    definitions = {tool["name"]: tool for tool in result["result"]["tools"]}

    schema = definitions["index.route"]["inputSchema"]
    assert schema["required"] == ["root", "paths"]
    assert schema["properties"]["paths"]["items"] == {"type": "string"}


def test_route_mcp_empty_path_returns_route_receipt(tmp_path):
    _repo(tmp_path / "app", "app", body_files=1)

    response = _mcp_route({"root": str(tmp_path), "paths": [""]})

    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "index.route/v1"
    assert payload["status"] == "UNVERIFIABLE"
    assert payload["failure_codes"] == ["no_selected_repositories"]
    assert payload["selection"]["selected"] == []
    assert payload["selection"]["rejected"] == [
        {"path": "", "reason_code": "empty-path", "rule_ref": "route.explicit_path.nonempty"}
    ]
    _assert_reconciles(payload)

