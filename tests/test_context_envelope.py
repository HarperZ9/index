from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from index_graph.cli import main
from index_graph.context.envelope import build_context_envelope
from index_graph.freshness import workspace_fingerprint
from index_graph.graph.build import DependencyGraph, RepoNode, build_graph
from index_graph.graph.edges import Edge, Signal

from test_bench import _repo


def _workspace(tmp_path):
    _repo(tmp_path / "app", "app", dep="lib", body_files=2)
    _repo(tmp_path / "lib", "lib", body_files=2)
    _repo(tmp_path / "docs", "docs", body_files=2)
    return {"app": tmp_path / "app", "lib": tmp_path / "lib", "docs": tmp_path / "docs"}

def _high_ref_workspace(tmp_path, *, refs=120):
    repo = tmp_path / "canon"
    (repo / ".git").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        "[project]\nname = \"canon\"\nversion = \"0\"\n",
        encoding="utf-8",
    )
    imports = "\n".join(f"import ext_{i:03d}" for i in range(refs))
    (repo / "main.py").write_text(imports + "\n", encoding="utf-8")
    return repo

def _high_ref_graph_with_prior_omission(tmp_path, *, refs=160):
    canon = _high_ref_graph(tmp_path, refs=refs)
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "README.md").write_text("# docs\n", encoding="utf-8")
    docs_node = RepoNode(
        "docs",
        str(docs),
        ("docs",),
        frozenset({"docs"}),
        "documentation repo outside focused context",
        frozenset({"README.md"}),
    )
    return DependencyGraph(
        repos=canon.repos + (docs_node,),
        edges=canon.edges,
        roles={"canon": ("application",), "docs": ("documentation",)},
        warnings=(),
    )

def _high_ref_graph(tmp_path, *, refs=96):
    repo = tmp_path / "canon"
    (repo / "refs").mkdir(parents=True)
    (repo / "README.md").write_text("# canon\n\nsource-ref fixture\n", encoding="utf-8")
    edges = []
    for i in range(refs):
        rel = f"refs/ref-{i:03d}-snow-☃.txt"
        (repo / rel).write_text(
            f"ref {i}: unicode=☃ quotes=\"yes\" slash=\\\\ newline\\n",
            encoding="utf-8",
        )
        edges.append(
            Edge(
                "canon",
                None,
                f"external-{i:03d}",
                True,
                "moderate",
                (Signal("manifest", rel, i + 1, f"external-{i:03d}"),),
            )
        )
    return DependencyGraph(
        repos=(
            RepoNode(
                "canon",
                str(repo),
                ("python",),
                frozenset({"canon"}),
                "large source-ref fixture",
                frozenset({"README.md"}),
            ),
        ),
        edges=tuple(edges),
        roles={},
        warnings=(),
    )


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
    assert env["failure_codes"] == ["budget_exceeded", "budget_overflow"]
    assert all(item["failure_code"] for item in env["omitted"])
    assert {item["failure_code"] for item in env["omitted"]} == {"budget_exceeded"}


def test_context_envelope_marks_budget_omissions(tmp_path):
    graph = build_graph(_workspace(tmp_path))

    env = build_context_envelope(graph, root=tmp_path, token_budget=55)

    assert env["verification_verdict"] == "UNVERIFIABLE"
    assert env["retained"]
    assert env["omitted"]
    assert any(item["reason"] == "budget_exceeded" for item in env["omitted"])
    assert env["failure_codes"] == ["budget_exceeded", "budget_overflow"]


def test_context_envelope_carries_selection_and_freshness_receipts(tmp_path):
    repo_paths = _workspace(tmp_path)
    graph = build_graph(repo_paths)

    env = build_context_envelope(graph, root=tmp_path, token_budget=500, focus="app", hops=1)
    stamp = workspace_fingerprint(repo_paths)

    assert env["selection"] == {
        "mode": "focused",
        "candidate_repos": 3,
        "selected_repos": 2,
        "retained_repos": 2,
        "omitted_repos": 1,
        "retained_names": ["app", "lib"],
        "omitted_failure_codes": ["outside_focus_or_budget"],
    }
    assert env["freshness"]["schema"] == "index.context-envelope-freshness/v1"
    assert env["freshness"]["source_schema"] == "index.freshness/1"
    assert env["freshness"]["workspace_root_sha256"] == stamp["root"]
    assert env["freshness"]["repo_count"] == 3
    assert set(env["freshness"]["retained_repo_sha256"]) == {"app", "lib"}
    assert "docs" not in env["freshness"]["retained_repo_sha256"]
    assert env["recheck"]["freshness_root_sha256"] == stamp["root"]


def test_context_envelope_cli_json(tmp_path, capsys):
    _workspace(tmp_path)

    assert main(["context-envelope", "--root", str(tmp_path), "--budget", "500",
                 "--focus", "app", "--hops", "1", "--json"]) == 0
    env = json.loads(capsys.readouterr().out)

    assert env["schema"] == "project-telos.context-envelope/v1"
    assert env["focus"]["repo"] == "app"
    assert env["budget"]["token_budget"] == 500


def test_forced_first_item_overflow_is_reported_not_capped(tmp_path):
    # token_budget=1 forces the first repo (retained even over budget). The
    # reported approx_tokens must be the TRUE cost, not capped to the budget,
    # and a budget_overflow failure code must fire so the verdict is not MATCH.
    graph = build_graph(_workspace(tmp_path))
    env = build_context_envelope(graph, root=tmp_path, token_budget=1)
    assert env["budget"]["approx_tokens"] > 1, "the true cost must not be capped to the budget"
    assert "budget_overflow" in env["failure_codes"]
    assert env["verification_verdict"] == "UNVERIFIABLE"


def test_packet_tokens_distinct_from_retained_and_names_the_scope(tmp_path):
    graph = build_graph(_workspace(tmp_path))
    env = build_context_envelope(graph, root=tmp_path, token_budget=1000)
    b = env["budget"]
    # approx_tokens bounds the retained selection; packet_approx_tokens is the
    # whole emitted dict, which carries more, so it is >= the retained cost
    assert "packet_approx_tokens" in b
    assert b["packet_approx_tokens"] >= b["approx_tokens"]


def test_bounded_output_leaves_small_packets_lossless_and_measures_wrapper(tmp_path):
    graph = build_graph(_workspace(tmp_path))
    default = build_context_envelope(graph, root=tmp_path, token_budget=5000)

    env = build_context_envelope(
        graph, root=tmp_path, token_budget=5000, bounded_output=True)

    assert env["context_policy"]["output_policy"] == "bounded_packet"
    assert env["retained"] == default["retained"]
    assert env["source_ref_omissions"] == []
    measurement = env["budget"]["packet_measurement"]
    assert measurement["scope"] == "entire_serialized_context_envelope"
    assert measurement["unit"] == "serialized_utf8_json_bytes_ceiling_div_4"
    assert "not model-tokenizer output" in measurement["boundary"]
    actual_bytes = len(json.dumps(env, sort_keys=True).encode("utf-8"))
    assert measurement["serialized_bytes"] == actual_bytes
    assert env["budget"]["packet_approx_tokens"] == math.ceil(actual_bytes / 4)
    assert env["budget"]["packet_approx_tokens"] <= 5000


def test_default_keeps_forced_first_full_source_refs_when_over_budget(tmp_path):
    graph = _high_ref_graph(tmp_path, refs=80)

    env = build_context_envelope(
        graph, root=tmp_path, token_budget=900, focus="canon", hops=0)

    assert env["verification_verdict"] == "UNVERIFIABLE"
    assert "budget_overflow" in env["failure_codes"]
    assert len(env["retained"]) == 1
    assert len(env["retained"][0]["source_refs"]) == 80
    assert "source_ref_omissions" not in env
    assert env["budget"]["packet_approx_tokens"] > 900


def test_bounded_output_compacts_high_ref_packet_with_omission_handles(tmp_path):
    graph = _high_ref_graph(tmp_path, refs=96)

    env = build_context_envelope(
        graph, root=tmp_path, token_budget=900, focus="canon", hops=0,
        bounded_output=True,
    )

    assert env["verification_verdict"] == "UNVERIFIABLE"
    assert "output_budget_exceeded" in env["failure_codes"]
    assert env["budget"]["packet_approx_tokens"] <= 900
    retained_refs = env["retained"][0]["source_refs"]
    assert len(retained_refs) < 96
    assert len(retained_refs) <= 1
    omission = env["source_ref_omissions"][0]
    assert omission["repo"] == "canon"
    assert omission["failure_code"] == "output_budget_exceeded"
    assert omission["total_source_refs"] == 96
    assert omission["included_source_refs"] == len(retained_refs)
    assert omission["omitted_source_refs"] == 96 - len(retained_refs)
    assert len(omission["source_refs_sha256"]) == 64
    assert omission["expand"]["tool"] == "index.context.envelope"
    assert omission["expand"]["arguments"]["bounded_output"] is False
    assert omission["expand"]["arguments"]["budget"] >= env["budget"]["pre_compaction_packet_approx_tokens"]
    assert omission["reissue"]["arguments"]["bounded_output"] is True
    assert omission["reissue"]["arguments"]["focus"] == "canon"
    assert omission["provenance"]["retained_repo_sha256"] == \
        env["freshness"]["retained_repo_sha256"]["canon"]


def test_bounded_output_measurement_accounts_for_utf8_and_json_escaping(tmp_path):
    graph = _high_ref_graph(tmp_path, refs=4)

    env = build_context_envelope(
        graph, root=tmp_path, token_budget=3000, focus="canon",
        bounded_output=True,
    )

    raw = json.dumps(env, sort_keys=True).encode("utf-8")
    assert b"\\u2603" in raw
    measurement = env["budget"]["packet_measurement"]
    assert measurement["serialized_bytes"] == len(raw)
    assert env["budget"]["packet_approx_tokens"] == math.ceil(len(raw) / 4)


def test_bounded_output_rejects_tiny_budget_that_cannot_hold_receipt(tmp_path):
    graph = _high_ref_graph(tmp_path, refs=4)

    with pytest.raises(ValueError, match="bounded_output budget too small"):
        build_context_envelope(
            graph, root=tmp_path, token_budget=1, focus="canon",
            bounded_output=True,
        )


def test_context_envelope_cli_bounded_output_json(tmp_path, capsys):
    _workspace(tmp_path)

    assert main([
        "context-envelope", "--root", str(tmp_path), "--budget", "5000",
        "--bounded-output", "--json",
    ]) == 0
    env = json.loads(capsys.readouterr().out)

    assert env["context_policy"]["output_policy"] == "bounded_packet"
    assert env["budget"]["packet_approx_tokens"] <= 5000


def test_context_envelope_cli_bounded_output_caps_actual_stdout_transport(tmp_path, capsys):
    # Catches measuring only the internal envelope JSON while CLI emits pretty JSON plus newline.
    _high_ref_workspace(tmp_path, refs=120)
    budget = 850

    assert main([
        "context-envelope", "--root", str(tmp_path), "--focus", "canon",
        "--hops", "0", "--budget", str(budget), "--bounded-output", "--json",
    ]) == 0
    out = capsys.readouterr().out
    actual_tokens = math.ceil(len(out.encode("utf-8")) / 4)
    env = json.loads(out)

    assert actual_tokens <= budget
    measurement = env["budget"]["packet_measurement"]
    assert measurement["scope"] == "cli_json_stdout"
    assert measurement["serialized_bytes"] == len(out.encode("utf-8"))
    assert env["budget"]["packet_approx_tokens"] == actual_tokens


def test_context_envelope_cli_bounded_output_caps_subprocess_stdout_bytes(tmp_path):
    # Catches Windows newline translation making actual subprocess stdout exceed the reported budget.
    _high_ref_workspace(tmp_path, refs=120)
    budget = 850
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "index_graph.cli",
            "context-envelope",
            "--root",
            str(tmp_path),
            "--focus",
            "canon",
            "--hops",
            "0",
            "--budget",
            str(budget),
            "--bounded-output",
            "--json",
        ],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    actual_tokens = math.ceil(len(result.stdout) / 4)
    env_payload = json.loads(result.stdout.decode("utf-8"))
    measurement = env_payload["budget"]["packet_measurement"]
    assert measurement["scope"] == "cli_json_stdout"
    assert measurement["serialized_bytes"] == len(result.stdout)
    assert env_payload["budget"]["packet_approx_tokens"] == actual_tokens
    assert actual_tokens <= budget


def test_minimal_bounded_receipt_preserves_preexisting_omitted_repo_metadata(tmp_path):
    # Catches minimal fallback rebuilding omissions from retained repos and losing prior focus omissions.
    graph = _high_ref_graph_with_prior_omission(tmp_path, refs=180)

    env = build_context_envelope(
        graph, root=tmp_path, token_budget=850, focus="canon", hops=0,
        bounded_output=True,
    )

    assert env["retained"] == []
    omitted = {item["name"]: item for item in env["omitted"]}
    assert omitted["docs"]["failure_code"] == "outside_focus_or_budget"
    assert omitted["canon"]["failure_code"] == "output_budget_exceeded"
    assert env["selection"]["omitted_repos"] == 2
    assert set(env["selection"]["omitted_failure_codes"]) >= {
        "outside_focus_or_budget",
        "output_budget_exceeded",
    }
