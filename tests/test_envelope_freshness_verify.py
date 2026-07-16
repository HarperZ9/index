"""A context envelope carries freshness receipts and a recheck command string, but the
package shipped no function that re-derives them. verify_envelope_freshness closes that:
it re-fingerprints the workspace and confirms the envelope is still current, so a cached
envelope that went stale (the workspace changed under it) is caught, named, not trusted."""
from __future__ import annotations

from index_graph.context.envelope import (build_context_envelope,
                                          verify_envelope_freshness)
from index_graph.graph.build import build_graph

from test_bench import _repo


def _workspace(tmp_path):
    _repo(tmp_path / "app", "app", dep="lib", body_files=2)
    _repo(tmp_path / "lib", "lib", body_files=2)
    return {"app": tmp_path / "app", "lib": tmp_path / "lib"}


def test_an_unchanged_workspace_verifies_fresh(tmp_path):
    graph = build_graph(_workspace(tmp_path))
    env = build_context_envelope(graph, root=tmp_path, token_budget=100000)
    v = verify_envelope_freshness(env, graph)
    assert v["fresh"] is True and v["verdict"] == "MATCH"
    assert v["workspace_root_ok"] is True and v["drifted_repos"] == []


def test_a_changed_workspace_drifts_and_names_the_repo(tmp_path):
    paths = _workspace(tmp_path)
    env = build_context_envelope(build_graph(paths), root=tmp_path, token_budget=100000)
    # a source file lands in lib AFTER the envelope was sealed
    (paths["lib"] / "added.py").write_text("def extra():\n    return 1\n", encoding="utf-8")
    v = verify_envelope_freshness(env, build_graph(paths))
    assert v["fresh"] is False and v["verdict"] == "DRIFT"
    assert v["workspace_root_ok"] is False
    assert "lib" in v["drifted_repos"]
    assert v["expected_root_sha256"] != v["actual_root_sha256"]


def test_cli_verify_flag_exits_zero_when_fresh_and_one_on_drift(tmp_path):
    import json

    from index_graph.cli import main
    paths = _workspace(tmp_path)
    env = build_context_envelope(build_graph(paths), root=tmp_path, token_budget=100000)
    ef = tmp_path / "env.json"
    ef.write_text(json.dumps(env), encoding="utf-8")
    assert main(["context-envelope", "--verify", str(ef), "--root", str(tmp_path)]) == 0
    (paths["lib"] / "added2.py").write_text("y = 2\n", encoding="utf-8")   # workspace moves
    assert main(["context-envelope", "--verify", str(ef), "--root", str(tmp_path)]) == 1
