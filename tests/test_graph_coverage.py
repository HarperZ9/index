import errno
import json
from pathlib import Path

import pytest

from index_graph.graph.build import build_graph


def _repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (repo / "main.py").write_text("import alpha\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    return repo


@pytest.mark.parametrize("use_cache", [False, True])
def test_unreadable_source_fails_complete_graph_without_caching(tmp_path, monkeypatch, use_cache):
    repo = _repo(tmp_path, monkeypatch)
    source = repo / "flaky.py"
    source.write_text("import beta\n", encoding="utf-8")
    original = Path.read_bytes

    def read(path):
        if path == source:
            raise PermissionError(errno.EACCES, "private diagnostic excluded", str(source))
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    progress = []
    with pytest.raises(RuntimeError, match="graph source read failed") as caught:
        build_graph({"sample": repo}, use_cache=use_cache, on_progress=progress.append)
    assert str(tmp_path) not in str(caught.value)
    assert "private diagnostic" not in str(caught.value)
    assert progress[-1].phase == "failed"
    assert not list((tmp_path / "cache").glob("*.json"))


def test_unreadable_subtree_cannot_return_complete_graph(tmp_path, monkeypatch):
    import index_graph.graph.walk as walk

    repo = _repo(tmp_path, monkeypatch)
    hidden = repo / "hidden"
    hidden.mkdir()
    (hidden / "secret.py").write_text("import beta\n", encoding="utf-8")
    original = walk.os.walk

    def broken(root, *args, **kwargs):
        for directory, directories, files in original(root, *args, **kwargs):
            if Path(directory) == repo:
                directories.remove("hidden")
                kwargs["onerror"](PermissionError(errno.EACCES, "denied", str(hidden)))
            yield directory, directories, files

    monkeypatch.setattr(walk.os, "walk", broken)
    progress = []
    with pytest.raises(RuntimeError, match="graph source traversal failed"):
        build_graph({"sample": repo}, use_cache=False, on_progress=progress.append)
    assert progress[-1].phase == "failed"
    assert not any(event.phase == "complete" for event in progress)


def test_cli_and_mcp_report_unverifiable_source_coverage(tmp_path, monkeypatch, capsys):
    from index_graph.cli import main
    from index_graph.mcp import handle_request

    repo = _repo(tmp_path, monkeypatch)
    source = repo / "main.py"
    original = Path.read_bytes

    def read(path):
        if path == source:
            raise PermissionError(errno.EACCES, "denied", str(source))
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    assert main(["graph", "--root", str(tmp_path), "--json"]) == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "UNVERIFIABLE"
    assert receipt["error_type"] == "GraphSourceError"
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "index_graph", "arguments": {
            "root": str(tmp_path), "no_cache": True}}})
    assert response["result"]["isError"] is True
    error = json.loads(response["result"]["content"][0]["text"])
    assert error["status"] == "UNVERIFIABLE"
    assert error["error_type"] == "GraphSourceError"
