import json

from index_graph.cli import main


def test_status_json_is_action_envelope(capsys):
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "project-telos.flagship-action/v1"
    assert payload["tool"] == "index"
    assert payload["native"]["role"] == "structure-context"
    assert "index.doctor" in payload["native"]["mcp_tools"]
    assert "index.context.envelope" in payload["native"]["mcp_tools"]
    assert "context-envelope" in payload["native"]["commands"]
    contracts = payload["native"]["telos_contracts"]
    assert "CLI JSON" in contracts["host_surfaces"]
    assert "project-telos.context-envelope/v1" in contracts["schemas"]
    assert "creative" in contracts["workflow_domains"]
    assert "dormant engine parts" in contracts["second_brain_role"]
    assert "selection summaries" in contracts["second_brain_role"]
    assert "freshness roots" in contracts["second_brain_role"]


def test_doctor_human_prints_next_action(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("status=MATCH tool=index command=doctor")
    assert "next: forum route" in out


def test_doctor_probes_mcp_map_surface(capsys):
    assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    checks = {check["name"]: check for check in payload["native"]["checks"]}
    assert checks["mcp_map_probe"]["status"] == "MATCH"
    assert checks["mcp_map_probe"]["repo_count"] == 1
    assert checks["mcp_map_probe"]["absolute_paths_included"] is False


def test_demo_json_names_map_command(capsys):
    assert main(["demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["native"]["command"] == "index map --root <workspace> --json"
