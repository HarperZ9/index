"""Falsifiers for the Context Lens.

The load-bearing one: the replay (the rule the page's slider runs) must
reproduce build_context_envelope's retained set EXACTLY at every budget.
If it ever diverges, the lens is showing a fiction and must not ship.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from index_graph.context.envelope import build_context_envelope
from index_graph.context.lens import build_lens_pack, replay_retained
from index_graph.graph.build import build_graph
from index_graph.viz.lens_html import render_lens_html


@pytest.fixture
def workspace(tmp_path):
    """Three tiny repos with real dependency evidence a -> b -> c."""
    for name, dep in (("alpha", "beta"), ("beta", "gamma"), ("gamma", None)):
        repo = tmp_path / name
        repo.mkdir()
        (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        body = {"name": name, "version": "0.0.1"}
        if dep:
            body["dependencies"] = {dep: "*"}
        (repo / "package.json").write_text(json.dumps(body), encoding="utf-8")
    return tmp_path


def _graph(workspace):
    return build_graph({p.name: p for p in sorted(workspace.iterdir())})


def test_replay_matches_envelope_at_every_budget(workspace):
    # THE contract: slider output == CLI output, across the whole budget range
    graph = _graph(workspace)
    lens = build_lens_pack(graph, root=workspace, token_budget=1200)
    order = lens["replay"]["order"]
    base = lens["replay"]["base_tokens"]
    hi = base + sum(o["cost"] for o in order) + 50
    for budget in range(1, hi, 7):
        env = build_context_envelope(graph, root=workspace, token_budget=budget)
        expected = [item["name"] for item in env["retained"]]
        assert replay_retained(order, base, budget) == expected, (
            f"replay diverged from the envelope at budget={budget}")


def test_pack_is_deterministic(workspace):
    graph = _graph(workspace)
    a = build_lens_pack(graph, root=workspace, token_budget=800)
    b = build_lens_pack(graph, root=workspace, token_budget=800)
    assert a == b
    assert a["receipt_sha256"] == b["receipt_sha256"]


def test_html_renders_deterministically_and_self_contained(workspace):
    graph = _graph(workspace)
    lens = build_lens_pack(graph, root=workspace, token_budget=800)
    page_a = render_lens_html(lens)
    page_b = render_lens_html(lens)
    assert page_a == page_b
    # self-contained: no external fetches of any kind
    for marker in ("http://", "https://", "src=", "@import", "url("):
        assert marker not in page_a, f"external reference marker found: {marker}"
    assert lens["receipt_sha256"] in page_a          # the receipt is on the page
    assert "index context-envelope" in page_a        # and the re-check command


def test_omissions_carry_failure_codes(workspace):
    graph = _graph(workspace)
    # a budget of 1 forces the greedy floor: one retained, rest budget_exceeded
    lens = build_lens_pack(graph, root=workspace, token_budget=1)
    env = lens["envelope"]
    assert len(env["retained"]) == 1
    assert env["omitted"], "tiny budget must omit repos"
    assert all(o["failure_code"] == "budget_exceeded" for o in env["omitted"])
    assert env["verification_verdict"] == "UNVERIFIABLE"   # never rounded up


def test_focus_scopes_the_replay_order(workspace):
    # closure is bidirectional: 1 hop from gamma = {gamma, beta}; alpha is 2 out
    graph = _graph(workspace)
    lens = build_lens_pack(graph, root=workspace, token_budget=1200,
                           focus="gamma", hops=1)
    names = {o["name"] for o in lens["replay"]["order"]}
    assert names == {"beta", "gamma"}
    out_reasons = {o["name"]: o["reason"] for o in lens["envelope"]["omitted"]}
    assert out_reasons.get("alpha") == "outside_focus_or_budget"


def test_cli_lens_writes_html(workspace, tmp_path, capsys):
    from index_graph.cli_handlers.context import cmd_lens

    class Args:
        root = workspace
        budget = 800
        focus = None
        hops = None
        json = False
        out = str(tmp_path / "lens.html")

    assert cmd_lens(Args()) == 0
    page = Path(Args.out).read_text(encoding="utf-8")
    assert "Context Lens" in page and "RETAINED" in page and "OMITTED" in page
    assert "context lens ->" in capsys.readouterr().out
