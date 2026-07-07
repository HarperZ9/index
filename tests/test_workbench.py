"""Falsifiers for the unified workbench.

Load-bearing: (1) the lens replay inside the workbench is the SAME contract as
the standalone lens (parity with build_context_envelope); (2) spine ingestion
fails closed — an invalid envelope is skipped with its reason, never rendered
as a peer; (3) the page is deterministic and self-contained.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from index_graph.context.envelope import build_context_envelope
from index_graph.context.lens import replay_retained
from index_graph.graph.build import build_graph
from index_graph.knowledge.docs import discover_docs
from index_graph.viz.workbench_html import render_workbench_html
from index_graph.workbench import build_workbench_pack, load_spine


@pytest.fixture
def workspace(tmp_path):
    for name, dep in (("alpha", "beta"), ("beta", "gamma"), ("gamma", None)):
        repo = tmp_path / name
        repo.mkdir()
        (repo / "README.md").write_text(
            f"# {name}\n\nThe {name} service. See [[beta]].\n", encoding="utf-8")
        body = {"name": name, "version": "0.0.1"}
        if dep:
            body["dependencies"] = {dep: "*"}
        (repo / "package.json").write_text(json.dumps(body), encoding="utf-8")
    return tmp_path


def _build(workspace, **kw):
    paths = {p.name: p for p in sorted(workspace.iterdir()) if p.is_dir()}
    graph = build_graph(paths)
    docs = discover_docs(workspace)
    repo_dirs = {n: p.name for n, p in paths.items()}
    return build_workbench_pack(graph, docs, repo_dirs, root=workspace, **kw)


def test_pack_composes_every_surface(workspace):
    wb = _build(workspace)
    for key in ("summary", "repos", "docs", "doc_html", "knowledge_edges",
                "backlinks", "cycles", "freshness", "lens", "spine",
                "receipt_sha256", "svg"):
        assert key in wb, f"surface missing from the pack: {key}"
    assert wb["summary"]["repos"] == 3
    names = {r["name"] for r in wb["repos"]}
    assert names == {"alpha", "beta", "gamma"}


def test_dependency_rows_carry_evidence(workspace):
    wb = _build(workspace)
    alpha = next(r for r in wb["repos"] if r["name"] == "alpha")
    assert alpha["depends_on"], "alpha must show its beta dependency"
    dep = alpha["depends_on"][0]
    assert dep["to"] == "beta"
    assert dep["evidence"], "the edge must carry file:line evidence"
    assert dep["evidence"][0]["file"]


def test_lens_replay_parity_with_envelope(workspace):
    wb = _build(workspace, token_budget=1200)
    order = wb["lens"]["replay"]["order"]
    base = wb["lens"]["replay"]["base_tokens"]
    paths = {p.name: p for p in sorted(workspace.iterdir()) if p.is_dir()}
    graph = build_graph(paths)
    hi = base + sum(o["cost"] for o in order) + 40
    for budget in range(1, hi, 9):
        env = build_context_envelope(graph, root=workspace, token_budget=budget)
        assert replay_retained(order, base, budget) == \
            [i["name"] for i in env["retained"]]


def test_spine_ingests_valid_and_fails_closed_on_invalid(workspace, tmp_path):
    spine = tmp_path / "spine"
    spine.mkdir()
    (spine / "gather.json").write_text(json.dumps({
        "schema": "project-telos.flagship-action/v1", "tool": "gather",
        "tool_version": "1.6.0", "command": "doctor", "status": "MATCH",
        "native": {"checks": [{"name": "json_receipts", "status": "MATCH"}]},
        "next_actions": [{"tool": "crucible", "action": "assess",
                          "reason": "verify claims"}]}), encoding="utf-8")
    (spine / "impostor.json").write_text(json.dumps(
        {"schema": "something-else/v9", "hello": "world"}), encoding="utf-8")
    (spine / "broken.json").write_text("{not json", encoding="utf-8")
    sp = load_spine(spine, workspace)
    assert [t["tool"] for t in sp["tools"]] == ["gather"]
    assert sp["ring"] == [{"from": "gather", "to": "crucible",
                           "action": "assess", "reason": "verify claims"}]
    reasons = {s["file"]: s["reason"] for s in sp["skipped"]}
    assert "impostor.json" in reasons and "envelope" in reasons["impostor.json"]
    assert "broken.json" in reasons and "unreadable" in reasons["broken.json"]


def test_spine_detects_forum_ledger_without_parsing_it(workspace):
    ledger = workspace / ".telos" / "forum-ledger"
    ledger.mkdir(parents=True)
    (ledger / "entry-1.json").write_text("{}", encoding="utf-8")
    sp = load_spine(None, workspace)
    (surface,) = sp["peer_surfaces"]
    assert surface["peer"] == "forum" and surface["entries"] == 1
    assert "forum" in surface["inspect"]          # the peer's own command, not ours


def test_html_is_deterministic_and_self_contained(workspace):
    wb = _build(workspace)
    a = render_workbench_html(wb)
    assert a == render_workbench_html(wb)
    for marker in ("http://", "https://", "@import", "fetch(", "src="):
        assert marker not in a.replace('xmlns="http://www.w3.org/2000/svg"', ""), \
            f"external reference marker: {marker}"
    assert wb["receipt_sha256"] in a
    # every view is present in the shell
    for view in ("view-overview", "view-map", "view-docs", "view-lens",
                 "view-health", "view-spine"):
        assert view in a


def test_receipt_seals_data_not_svg(workspace):
    wb1 = _build(workspace)
    wb2 = _build(workspace)
    assert wb1["receipt_sha256"] == wb2["receipt_sha256"]


def test_cli_workbench_writes_html(workspace, tmp_path, capsys):
    from index_graph.cli_handlers.maps import cmd_workbench

    class Args:
        root = workspace
        budget = 800
        spine_dir = None
        json = False
        out = str(tmp_path / "wb.html")

    assert cmd_workbench(Args()) == 0
    page = Path(Args.out).read_text(encoding="utf-8")
    assert "index · workbench" in page and "Context Lens" in page
    assert "workbench ->" in capsys.readouterr().out
