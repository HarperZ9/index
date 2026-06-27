import json

from index_graph.cli import main


def test_status_json_is_action_envelope(capsys):
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "project-telos.flagship-action/v1"
    assert payload["tool"] == "index"
    assert payload["native"]["role"] == "structure-context"
    assert "index.doctor" in payload["native"]["mcp_tools"]


def test_doctor_human_prints_next_action(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("status=MATCH tool=index command=doctor")
    assert "next: forum route" in out


def test_demo_json_names_map_command(capsys):
    assert main(["demo", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["native"]["command"] == "index map --root <workspace> --json"
