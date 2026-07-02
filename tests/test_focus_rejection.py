"""Tests for the typed focus rejection receipt (index.focus-rejection/v1).

A free-form focus selector that resolves to no repo must fail TYPED: a
receipt naming the unresolved selector, a reason code from a closed set,
and a bounded candidate list, following the index.path-selection/v1
typed-rejection precedent. A bare "unknown focus repo" string is not a
contract another tool can act on.
"""
import json

import pytest

from index_graph.cli import main
from index_graph.context.envelope import build_context_envelope
from index_graph.context.focus import (
    CANDIDATE_LIMIT,
    REASON_CODES,
    REJECTION_SCHEMA,
    FocusRejection,
    focus_rejection,
    resolve_focus,
)
from index_graph.graph.build import build_graph
from index_graph.mcp import handle_request


def _repo(d, name, dep=None):
    (d / ".git").mkdir(parents=True)
    deps = f'["{dep}"]' if dep else "[]"
    (d / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\ndependencies = {deps}\n',
        encoding="utf-8",
    )
    (d / "main.py").write_text((f"import {dep}\n") if dep else "x = 1\n", encoding="utf-8")
    return d


def _workspace(tmp_path):
    _repo(tmp_path / "gather", "gather", dep="forum")
    _repo(tmp_path / "forum", "forum")
    _repo(tmp_path / "crucible", "crucible")
    return tmp_path


# --- the receipt primitive ---


def test_reason_codes_are_the_closed_set():
    assert REASON_CODES == frozenset({"unresolved-focus", "empty-workspace"})


def test_rejection_receipt_shape_exact():
    receipt = focus_rejection("gath", ["gather", "forum", "crucible"])
    assert receipt == {
        "schema": REJECTION_SCHEMA,
        "selector": "gath",
        "reason_code": "unresolved-focus",
        "candidates": ["gather", "crucible", "forum"],
        "candidate_count": 3,
        "truncated": False,
    }


def test_candidates_are_bounded_and_truncation_is_declared():
    names = [f"repo-{i:02d}" for i in range(20)]
    receipt = focus_rejection("nomatch", names)
    assert len(receipt["candidates"]) == CANDIDATE_LIMIT
    assert receipt["candidate_count"] == 20
    assert receipt["truncated"] is True


def test_empty_workspace_has_its_own_reason_code():
    receipt = focus_rejection("anything", [])
    assert receipt["reason_code"] == "empty-workspace"
    assert receipt["candidates"] == []
    assert receipt["candidate_count"] == 0


def test_resolve_focus_returns_exact_match():
    assert resolve_focus("forum", {"forum", "gather"}) == "forum"


def test_resolve_focus_raises_typed_rejection_that_is_a_value_error():
    with pytest.raises(FocusRejection) as caught:
        resolve_focus("foruk", {"forum", "gather"})
    assert isinstance(caught.value, ValueError)
    receipt = caught.value.receipt
    assert receipt["schema"] == REJECTION_SCHEMA
    assert receipt["selector"] == "foruk"
    assert receipt["reason_code"] == "unresolved-focus"


# --- the envelope carries the receipt ---


def test_envelope_unresolved_focus_carries_the_receipt(tmp_path):
    root = _workspace(tmp_path)
    graph = build_graph({"gather": root / "gather", "forum": root / "forum",
                         "crucible": root / "crucible"})
    with pytest.raises(FocusRejection) as caught:
        build_context_envelope(graph, root=root, token_budget=500, focus="gathr")
    receipt = caught.value.receipt
    assert receipt["selector"] == "gathr"
    assert "gather" in receipt["candidates"]


# --- CLI faces: context, context-envelope, viz ---


def test_cli_context_unresolved_focus_emits_receipt_json(tmp_path, capsys):
    root = _workspace(tmp_path)
    rc = main(["context", "--root", str(root), "--focus", "gathr", "--json"])
    assert rc == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == REJECTION_SCHEMA
    assert receipt["selector"] == "gathr"
    assert receipt["reason_code"] == "unresolved-focus"
    assert "gather" in receipt["candidates"]


def test_cli_context_unresolved_focus_human_line_names_candidates(tmp_path, capsys):
    root = _workspace(tmp_path)
    rc = main(["context", "--root", str(root), "--focus", "gathr"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "gathr" in out and "unresolved-focus" in out and "gather" in out


def test_cli_context_envelope_unresolved_focus_emits_receipt(tmp_path, capsys):
    root = _workspace(tmp_path)
    rc = main(["context-envelope", "--root", str(root), "--focus", "gathr", "--json"])
    assert rc == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == REJECTION_SCHEMA
    assert receipt["selector"] == "gathr"


def test_cli_viz_unresolved_focus_renders_receipt(tmp_path, capsys):
    root = _workspace(tmp_path)
    rc = main(["viz", "--root", str(root), "--focus", "gathr",
               "--out", str(tmp_path / "x.html")])
    assert rc == 2
    out = capsys.readouterr().out
    assert "unresolved-focus" in out and "gather" in out


# --- MCP parity: a rejection is a payload, not a protocol error ---


def test_mcp_index_focus_unresolved_returns_receipt_not_error(tmp_path):
    root = _workspace(tmp_path)
    r = handle_request({"jsonrpc": "2.0", "id": 30, "method": "tools/call",
                        "params": {"name": "index_focus",
                                   "arguments": {"root": str(root), "repo": "gathr"}}})
    assert r["result"]["isError"] is False
    receipt = json.loads(r["result"]["content"][0]["text"])
    assert receipt["schema"] == REJECTION_SCHEMA
    assert receipt["selector"] == "gathr"
    assert "gather" in receipt["candidates"]


def test_mcp_context_envelope_unresolved_focus_returns_receipt(tmp_path):
    root = _workspace(tmp_path)
    r = handle_request({"jsonrpc": "2.0", "id": 31, "method": "tools/call",
                        "params": {"name": "index.context.envelope",
                                   "arguments": {"root": str(root), "focus": "gathr"}}})
    assert r["result"]["isError"] is False
    receipt = json.loads(r["result"]["content"][0]["text"])
    assert receipt["schema"] == REJECTION_SCHEMA
    assert receipt["selector"] == "gathr"
