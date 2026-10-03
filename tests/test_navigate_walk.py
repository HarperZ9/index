"""The navigator over a fixture repo, and its CLI and MCP faces."""
from __future__ import annotations

import json

import pytest

from index_graph.cli import main
from index_graph.mcp import handle_request
from index_graph.navigate import walk
from index_graph.navigate.api import outline_map, run_navigate
from index_graph.navigate.chooser import LexicalChooser
from index_graph.navigate.outline import build_outline
from navigate_fixtures import make_repo


@pytest.fixture()
def repo(tmp_path):
    return make_repo(tmp_path / "demo")


def check_navigation(navigate, outline) -> None:
    """The retry question lands on retry.py first, shows leaves only, and logs every question."""
    result = navigate(outline, "retry with exponential backoff", LexicalChooser(outline.idf),
                      max_files=3)
    assert result["files"][0] == "src/net/retry.py"
    assert len(result["files"]) == 3, "backtracking fills the file budget"
    assert len({leaf["file"] for leaf in result["leaves"]}) == len(result["leaves"])
    retry_text = outline.files["src/net/retry.py"]
    assert result["tokens_shown"] < -(-len(retry_text.encode()) // 4) * 3
    for step in result["path"]["steps"]:
        assert abs(sum(step["distribution"]) - 1) < 1e-4
        assert set(step["followed"]) <= set(step["options"]) and step["followed"]
    assert result["path"]["steps"][0]["node"] == "."


def test_navigation_finds_the_topic_and_records_the_path(repo):
    check_navigation(walk.navigate, build_outline(repo))


def test_navigation_check_catches_a_navigator_without_backtracking(repo, monkeypatch):
    original = walk._ask

    def no_backlog(*args):
        step, cost, kept, _deferred = original(*args)
        return step, cost, kept, []
    monkeypatch.setattr(walk, "_ask", no_backlog)
    with pytest.raises(AssertionError):
        check_navigation(walk.navigate, build_outline(repo))


def test_navigation_check_catches_a_navigator_that_ignores_the_chooser(repo):
    class Reversed(LexicalChooser):
        def choose(self, query, options):
            return list(reversed(super().choose(query, options)))
    outline = build_outline(repo)

    def mutant(outline, query, _chooser, **kw):
        return walk.navigate(outline, query, Reversed(outline.idf), **kw)
    with pytest.raises(AssertionError):
        check_navigation(mutant, outline)


def test_code_only_by_default_and_docs_on_request(repo):
    assert "README.md" not in build_outline(repo).files
    assert "README.md" in build_outline(repo, include_docs=True).files


def test_all_leaves_delivers_more_than_best_leaf(repo):
    best = run_navigate(repo, "retry backoff delay attempt", max_files=1)
    every = run_navigate(repo, "retry backoff delay attempt", max_files=1, all_leaves=True)
    assert len(best["leaves"]) == 1 and len(every["leaves"]) >= 1
    assert best["leaves"][0]["text"].startswith(("def ", "\"\"\"", "import"))
    assert every["tokens_shown"] >= best["tokens_shown"]
    with pytest.raises(ValueError):
        run_navigate(repo, "   ")


def test_outline_map_walks_down_to_a_leaf(repo):
    top = outline_map(repo)
    assert top["schema"] == "index.outline-map/v1" and top["node"] == "."
    src = next(e for e in top["entries"] if e["name"] == "src/")
    net = next(e for e in outline_map(repo, src["handle"]["node"])["entries"] if e["name"] == "net/")
    files = outline_map(repo, net["handle"]["node"])["entries"]
    retry = next(e for e in files if e["name"] == "retry.py")
    leaves = outline_map(repo, retry["handle"]["node"])["entries"]
    leaf = next(e for e in leaves if e["name"] == "retry_call")
    assert leaf["handle"]["file"] == "src/net/retry.py" and leaf["handle"]["start"] > 1
    detail = outline_map(repo, leaf["handle"]["node"])
    assert detail["entries"] == [] and "def retry_call" in detail["text"]
    with pytest.raises(KeyError):
        outline_map(repo, "no/such/node")


def _call(name, args):
    reply = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": name, "arguments": args}})
    return reply["result"]


def test_mcp_navigate_and_outline_map(repo):
    names = {t["name"] for t in handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}
    assert {"index.navigate", "index.outline-map"} <= names
    nav = _call("index.navigate", {"root": str(repo), "query": "parse http headers"})
    payload = json.loads(nav["content"][0]["text"])
    assert nav["isError"] is False and payload["files"][0] == "src/net/http.py"
    assert payload["leaves"][0]["id"].startswith("src/net/http.py::HttpClient")
    missing = _call("index.navigate", {"root": str(repo)})
    assert missing["isError"] is True


def test_cli_navigate_json(repo, capsys):
    rc = main(["navigate", str(repo), "cache expiry", "--json", "--files", "2"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "index.navigate/v1"
    assert payload["files"][0] == "src/store/cache.py" and len(payload["files"]) == 2
    assert main(["outline-map", str(repo), "--node", "src/store/"]) == 0
    assert "cache.py" in capsys.readouterr().out
