from __future__ import annotations

import hashlib
import json

from index_graph.cli import main
from index_graph.context.envelope import build_context_envelope
from index_graph.graph.build import build_graph

from test_bench import _repo


def _workspace(tmp_path):
    _repo(tmp_path / "app", "app", dep="lib", body_files=2)
    _repo(tmp_path / "lib", "lib", body_files=2)
    _repo(tmp_path / "docs", "docs", body_files=2)
    return {"app": tmp_path / "app", "lib": tmp_path / "lib", "docs": tmp_path / "docs"}


def test_context_envelope_is_budgeted_and_receipt_backed(tmp_path):
    graph = build_graph(_workspace(tmp_path))

    env = build_context_envelope(graph, root=tmp_path, token_budget=500, focus="app", hops=1)

    assert env["schema"] == "project-telos.context-envelope/v1"
    assert env["tool"] == "index.context.envelope"
    assert env["budget"]["token_budget"] == 500
    assert env["budget"]["approx_tokens"] <= 500
    assert env["budget"]["bytes_per_token"] == 4
    assert env["focus"] == {"repo": "app", "hops": 1}
    assert env["verification_verdict"] == "MATCH"
    assert env["receipts"][0]["kind"] == "graph-pack"
    assert env["receipts"][0]["sha256"]
    assert {item["name"] for item in env["retained"]} == {"app", "lib"}
    omitted = {item["name"]: item["reason"] for item in env["omitted"]}
    assert omitted == {"docs": "outside_focus_or_budget"}
    assert all(item["source_refs"] for item in env["retained"])
    assert env["privacy"]["raw_source_included"] is False
    assert "graph_pack_sha256" in env["recheck"]


def test_context_envelope_source_refs_are_verifiable_handles(tmp_path):
    graph = build_graph(_workspace(tmp_path))

    env = build_context_envelope(graph, root=tmp_path, token_budget=1000)

    refs = [ref for item in env["retained"] for ref in item["source_refs"]]
    assert refs
    manifest_ref = next(ref for ref in refs if ref["path"] == "app/pyproject.toml")
    expected_hash = hashlib.sha256((tmp_path / manifest_ref["path"]).read_bytes()).hexdigest()
    assert manifest_ref == {
        "schema": "project-telos.source-ref/v1",
        "repo": "app",
        "repo_path": "app",
        "path": "app/pyproject.toml",
        "kind": "manifest",
        "line": 4,
        "sha256": expected_hash,
        "expand": {
            "tool": "gather.docs",
            "arguments": {
                "path": "app/pyproject.toml",
                "scope": "index.context.envelope",
            },
        },
    }


def test_context_envelope_states_lossless_reference_policy(tmp_path):
    graph = build_graph(_workspace(tmp_path))

    env = build_context_envelope(graph, root=tmp_path, token_budget=55)

    assert env["context_policy"] == {
        "mode": "lossless_by_reference",
        "raw_payload_policy": "source_refs_only",
        "omission_policy": "explicit_failure_codes",
    }
    assert env["failure_codes"] == ["budget_exceeded"]
    assert all(item["failure_code"] for item in env["omitted"])
    assert {item["failure_code"] for item in env["omitted"]} == {"budget_exceeded"}


def test_context_envelope_marks_budget_omissions(tmp_path):
    graph = build_graph(_workspace(tmp_path))

    env = build_context_envelope(graph, root=tmp_path, token_budget=55)

    assert env["verification_verdict"] == "UNVERIFIABLE"
    assert env["retained"]
    assert env["omitted"]
    assert any(item["reason"] == "budget_exceeded" for item in env["omitted"])
    assert env["failure_codes"] == ["budget_exceeded"]


def test_context_envelope_cli_json(tmp_path, capsys):
    _workspace(tmp_path)

    assert main(["context-envelope", "--root", str(tmp_path), "--budget", "500",
                 "--focus", "app", "--hops", "1", "--json"]) == 0
    env = json.loads(capsys.readouterr().out)

    assert env["schema"] == "project-telos.context-envelope/v1"
    assert env["focus"]["repo"] == "app"
    assert env["budget"]["token_budget"] == 500
