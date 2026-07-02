"""CLI + MCP surface for the symbol graph."""
import json

from index_graph.cli import main
from index_graph.mcp import call_tool

from symbol_fixtures import write


def test_internals_symbols_json(tmp_path, capsys):
    write(tmp_path, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    rc = main(["internals-symbols", "--root", str(tmp_path), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "symbols" in data
    assert "calls" in data
    assert data["repo"] == tmp_path.name
    assert any(s["id"] == "mod::foo" for s in data["symbols"])


def test_internals_symbols_text(tmp_path, capsys):
    write(tmp_path, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    rc = main(["internals-symbols", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "symbols=" in out
    assert "calls=" in out


def test_mcp_symbol_graph(tmp_path):
    write(tmp_path, "pkg/__init__.py", "")
    write(tmp_path, "pkg/mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    out = json.loads(call_tool("index.symbol-graph", {"root": str(tmp_path)}))
    assert any(s["id"] == "pkg/mod::foo" for s in out["symbols"])


def test_mcp_symbol_definition(tmp_path):
    write(tmp_path, "mod.py", "def target():\n    pass\n")
    out = json.loads(call_tool("index.symbol-definition",
                               {"root": str(tmp_path), "symbol": "target"}))
    assert out["definitions"]
    assert out["definitions"][0]["file"] == "mod.py"
    assert out["definitions"][0]["line"] == 1


def test_mcp_symbol_references(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    out = json.loads(call_tool("index.symbol-references",
                               {"root": str(tmp_path), "symbol": "mod::foo"}))
    assert out["references"]
    assert out["references"][0]["from_symbol"] == "mod::bar"
    assert out["references"][0]["file"] == "mod.py"
