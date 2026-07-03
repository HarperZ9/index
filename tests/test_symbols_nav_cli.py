"""CLI (`index symbols`) and MCP surface for symbol-graph navigation."""
import json

from index_graph.cli import main
from index_graph.mcp import _tool_defs, call_tool

from symbol_fixtures import inheritance, write


def test_symbols_cli_default_reports_all_sections(tmp_path, capsys):
    inheritance(tmp_path)
    rc = main(["symbols", "Animal", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "definitions (1):" in out
    assert "references (" in out
    assert "implementations (2 subclasses" in out
    assert "base.py:1" in out


def test_symbols_cli_def_json(tmp_path, capsys):
    inheritance(tmp_path)
    rc = main(["symbols", "Animal::speak", "--root", str(tmp_path), "--def", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["query"] == "Animal::speak"
    assert data["definitions"][0]["id"] == "base::Animal::speak"
    assert data["definitions"][0]["file"] == "base.py"
    assert data["definitions"][0]["line"] == 2
    # A single-mode query carries only that section.
    assert "references" not in data
    assert "implementations" not in data


def test_symbols_cli_impls_json_carries_evidence(tmp_path, capsys):
    inheritance(tmp_path)
    rc = main(["symbols", "Animal::speak", "--root", str(tmp_path), "--impls", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    overs = data["implementations"]["overrides"]
    ids = {(o["child"], o["file"], o["line"]) for o in overs}
    assert ("dog::Dog::speak", "dog.py", 5) in ids
    assert ("cat::Cat::speak", "cat.py", 5) in ids


def test_symbols_cli_refs_only(tmp_path, capsys):
    write(tmp_path, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    rc = main(["symbols", "mod::foo", "--root", str(tmp_path), "--refs", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    ref = data["references"]["references"][0]
    assert ref["from_symbol"] == "mod::bar"
    assert ref["file"] == "mod.py"
    assert ref["line"] == 6


def test_symbols_cli_no_match_exits_2(tmp_path, capsys):
    inheritance(tmp_path)
    rc = main(["symbols", "Nonexistent", "--root", str(tmp_path), "--def"])
    assert rc == 2
    assert "definitions (0):" in capsys.readouterr().out


def test_mcp_symbol_implementations_tool_listed():
    names = {t["name"] for t in _tool_defs()}
    assert "index.symbol-implementations" in names


def test_mcp_symbol_implementations(tmp_path):
    inheritance(tmp_path)
    out = json.loads(call_tool("index.symbol-implementations",
                               {"root": str(tmp_path), "symbol": "Animal::speak"}))
    assert out["symbol"] == "Animal::speak"
    ids = {(o["child"], o["file"], o["line"]) for o in out["overrides"]}
    assert ("dog::Dog::speak", "dog.py", 5) in ids
    assert ("cat::Cat::speak", "cat.py", 5) in ids
    assert out["subclasses"] == []
