import json

from index_graph.cli import main


def test_status_json_is_action_envelope(capsys):
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "project-telos.flagship-action/v1"
    assert payload["tool"] == "index"
    assert payload["native"]["role"] == "structure-context"
    assert "index.doctor" in payload["native"]["mcp_tools"]
    contracts = payload["native"]["telos_contracts"]
    assert "CLI JSON" in contracts["host_surfaces"]
    assert "project-telos.context-envelope/v1" in contracts["schemas"]
    assert "creative" in contracts["workflow_domains"]
    assert "dormant engine parts" in contracts["second_brain_role"]


def test_doctor_human_prints_next_action(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("status=MATCH tool=index command=doctor")
    assert "next: forum route" in out


def test_demo_json_names_map_command(capsys):
    assert main(["demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["native"]["command"] == "index map --root <workspace> --json"
