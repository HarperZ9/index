"""CLI + MCP + status parity for `index wiki`, per the AGENTS.md alignment contract."""
import json

from index_graph.cli import main
from index_graph.mcp import handle_request

from wiki_fixtures import make_repo


def test_cli_wiki_json_prints_the_pack(tmp_path, capsys):
    root = make_repo(tmp_path / "demo")
    assert main(["wiki", "--root", str(root), "--format", "json"]) == 0
    pack = json.loads(capsys.readouterr().out)
    assert pack["schema"] == "index.wiki/1"
    assert {p["id"] for p in pack["pages"]} >= {"overview", "architecture", "docs"}


def test_cli_wiki_html_writes_the_artifact(tmp_path, capsys):
    root = make_repo(tmp_path / "demo")
    out = tmp_path / "wiki.html"
    assert main(["wiki", "--root", str(root), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert str(out) in capsys.readouterr().out


def test_cli_wiki_verify_exit_codes(tmp_path, capsys):
    root = make_repo(tmp_path / "demo")
    out = tmp_path / "wiki.json"
    assert main(["wiki", "--root", str(root), "--format", "json",
                 "--out", str(out)]) == 0
    capsys.readouterr()
    assert main(["wiki", "--verify", str(out), "--root", str(root)]) == 0
    assert "verdict=MATCH" in capsys.readouterr().out

    pack = json.loads(out.read_text(encoding="utf-8"))
    for page in pack["pages"]:
        if page["kind"] == "module":
            page["path"] = "forged.py"
            break
    out.write_text(json.dumps(pack), encoding="utf-8")
    assert main(["wiki", "--verify", str(out), "--root", str(root)]) == 1
    assert "verdict=DRIFT" in capsys.readouterr().out

    garbage = tmp_path / "garbage.json"
    garbage.write_text("[]", encoding="utf-8")
    assert main(["wiki", "--verify", str(garbage), "--root", str(root)]) == 2
    assert "verdict=UNVERIFIABLE" in capsys.readouterr().out

    # --json emits the re-checkable report
    assert main(["wiki", "--verify", str(out), "--root", str(root), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "index.wiki-verification/1"
    assert report["recheck"].startswith("index wiki --verify")


def test_mcp_lists_and_serves_index_wiki(tmp_path):
    r = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert "index.wiki" in {t["name"] for t in r["result"]["tools"]}
    root = make_repo(tmp_path / "demo")
    call = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                           "params": {"name": "index.wiki",
                                      "arguments": {"root": str(root)}}})
    assert call["result"]["isError"] is False
    pack = json.loads(call["result"]["content"][0]["text"])
    assert pack["schema"] == "index.wiki/1"

    artifact = tmp_path / "wiki.json"
    artifact.write_text(json.dumps(pack), encoding="utf-8")
    ver = handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "index.wiki",
                                     "arguments": {"root": str(root),
                                                   "verify": str(artifact)}}})
    assert ver["result"]["isError"] is False
    report = json.loads(ver["result"]["content"][0]["text"])
    assert report["schema"] == "index.wiki-verification/1"
    assert report["verdict"] == "MATCH"


def test_status_advertises_the_wiki_surface(capsys):
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "wiki" in payload["native"]["commands"]
    assert "index.wiki" in payload["native"]["mcp_tools"]
