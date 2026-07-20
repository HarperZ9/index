import hashlib
import json
from dataclasses import replace

import pytest

from index_graph.route.budget import WorkBudget
from index_graph.route.model import RouteRequest
from index_graph.route.scope import resolve_scope


def _repo(root, rel):
    repo = root / rel
    (repo / ".git").mkdir(parents=True)
    return repo


def test_explicit_path_is_root_relative_and_avoids_siblings(tmp_path):
    _repo(tmp_path, "public/index")
    _repo(tmp_path, "public/forum")
    request = RouteRequest.create(tmp_path, paths=["public/index"])
    result = resolve_scope(request, WorkBudget.start(5000))
    assert [candidate.id for candidate in result.selected] == ["public/index"]
    assert [candidate.id for candidate in result.candidates] == ["public/index"]


def test_explicit_dot_selects_repository_at_root(tmp_path):
    (tmp_path / ".git").mkdir()
    request = RouteRequest.create(tmp_path, paths=["."])
    result = resolve_scope(request, WorkBudget.start(5000))
    assert [candidate.id for candidate in result.selected] == ["."]


def test_explicit_paths_are_deduplicated_and_sorted(tmp_path):
    _repo(tmp_path, "public/b")
    _repo(tmp_path, "public/a")
    request = RouteRequest.create(
        tmp_path, paths=["public/b", "public/a", "public/b"]
    )
    result = resolve_scope(request, WorkBudget.start(5000))
    assert [candidate.id for candidate in result.selected] == [
        "public/a", "public/b",
    ]


def test_explicit_config_annotation_affects_the_bounded_shortlist(tmp_path):
    _repo(tmp_path, "public/a")
    _repo(tmp_path, "public/b")
    (tmp_path / ".index.toml").write_text(
        '[output.annotations]\n"public/b" = "router"\n', encoding="utf-8"
    )
    request = RouteRequest.create(
        tmp_path, paths=["public/a", "public/b"], query="router", max_repos=1
    )
    result = resolve_scope(request, WorkBudget.start(5000))
    assert [candidate.id for candidate in result.selected] == ["public/b"]


def test_explicit_path_outside_root_is_rejected_without_leaking_its_path(tmp_path):
    outside = _repo(tmp_path.parent, "outside-route-repo")
    with pytest.raises(ValueError, match="outside-root"):
        RouteRequest.create(tmp_path, paths=[str(outside)])
    valid = RouteRequest.create(tmp_path)
    request = replace(valid, paths=(str(outside),))
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.rejected[0]["reason_code"] == "outside-root"
    assert str(outside) not in str(result)
    assert result.reconciliation["verdict"] == "MATCH"
    assert result.reconciliation["counts"] == {
        "candidates": 1,
        "selected": 0,
        "rejected": 1,
        "omitted": 0,
    }


def test_repeated_malformed_explicit_path_is_booked_once(tmp_path):
    outside = _repo(tmp_path.parent, "outside-route-duplicate")
    request = replace(RouteRequest.create(tmp_path), paths=(str(outside), str(outside)))
    result = resolve_scope(request, WorkBudget.start(5000))
    assert len(result.candidates) == 1
    assert len(result.rejected) == 1
    assert result.reconciliation["verdict"] == "MATCH"


def test_valid_workspace_map_seeds_candidates_without_global_scan(tmp_path):
    _repo(tmp_path, "public/index")
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": root_hash,
        "repositories": [{
            "path": "public/index",
            "class": "public",
            "markers": ["README.md"],
        }],
    }), encoding="utf-8")
    request = RouteRequest.create(tmp_path, query="index")
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.selected[0].source == "workspace-map"
    assert "query:index" in result.selected[0].signals
    assert result.complete is False
    assert result.source["validation"] == "UNVERIFIED"


def test_repeated_malformed_map_row_is_booked_once(tmp_path):
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": root_hash,
        "repositories": [{"path": "../outside"}, {"path": "../outside"}],
    }), encoding="utf-8")
    result = resolve_scope(RouteRequest.create(tmp_path), WorkBudget.start(5000))
    assert len(result.candidates) == 1
    assert len(result.rejected) == 1
    assert result.reconciliation["verdict"] == "MATCH"


def test_map_metadata_remains_available_during_query_rescoring(tmp_path):
    _repo(tmp_path, "public/index")
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": root_hash,
        "repositories": [{"path": "public/index", "markers": ["router"]}],
    }), encoding="utf-8")
    request = RouteRequest.create(tmp_path, query="router")
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.selected[0].score == 1
    assert "query:router" in result.selected[0].signals


def test_strict_mode_validates_map_against_repository_discovery(tmp_path):
    _repo(tmp_path, "public/index")
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": root_hash,
        "repositories": [{"path": "public/index"}],
    }), encoding="utf-8")
    request = RouteRequest.create(tmp_path, freshness="strict")
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.complete is True
    assert result.source["validation"] == "FRESH"


def test_strict_map_with_invalid_row_uses_discovery_and_records_safe_drift(tmp_path):
    _repo(tmp_path, "public/index")
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": root_hash,
        "repositories": [{"path": "public/index"}, {"path": "../outside"}],
    }), encoding="utf-8")
    result = resolve_scope(
        RouteRequest.create(tmp_path, freshness="strict"), WorkBudget.start(5000)
    )
    assert [candidate.id for candidate in result.candidates] == ["public/index"]
    assert result.rejected == ()
    assert result.source["validation"] == "DRIFT"
    assert result.source["map_rejections"][0]["reason_code"] == "outside-root"
    assert "../outside" not in str(result.source["map_rejections"])


def test_query_scoring_uses_bounded_readme_title_and_matching_annotation(tmp_path):
    repo = _repo(tmp_path, "public/index")
    (repo / "README.md").write_text("# Evidence Router\n", encoding="utf-8")
    (tmp_path / ".index.toml").write_text(
        '[output.annotations]\n"public/index" = "bounded routing"\n',
        encoding="utf-8",
    )
    request = RouteRequest.create(tmp_path, query="evidence bounded")
    result = resolve_scope(request, WorkBudget.start(5000))
    assert result.selected[0].score == 2
    assert {"query:evidence", "query:bounded"} <= set(result.selected[0].signals)


def test_max_docs_zero_prevents_scope_readme_open(tmp_path):
    repo = _repo(tmp_path, "public/index")
    (repo / "README.md").write_text("# Evidence Router\n", encoding="utf-8")
    budget = WorkBudget.start(5000)
    request = RouteRequest.create(
        tmp_path, query="evidence", max_docs=0
    )
    result = resolve_scope(request, budget)
    assert result.selected[0].score == 0
    assert budget.counters["document_bodies_opened"] == 0


def test_readme_budget_exhaustion_marks_scope_incomplete(tmp_path):
    repo = _repo(tmp_path, "public/index")
    (repo / "README.md").write_text("# Evidence Router\n", encoding="utf-8")
    ticks = iter((0.0, 0.001, 0.005))
    budget = WorkBudget.start(5, clock=lambda: next(ticks))
    request = RouteRequest.create(tmp_path, paths=["public/index"], query="evidence")
    result = resolve_scope(request, budget)
    assert result.complete is False
    assert budget.exhausted_at == "docs.open"
    assert result.source["omissions"] == [{
        "reason_code": "budget-exhausted",
        "rule_ref": "route.query.readme",
        "boundary": "docs.open",
    }]


def test_discovery_budget_exhaustion_records_source_evidence_without_a_map(tmp_path):
    ticks = iter((0.0, 0.005))
    budget = WorkBudget.start(5, clock=lambda: next(ticks))
    result = resolve_scope(RouteRequest.create(tmp_path), budget)
    assert result.complete is False
    assert result.source["omissions"] == [{
        "reason_code": "budget-exhausted",
        "rule_ref": "route.discovery",
        "boundary": "scan.directory",
    }]


def test_strict_map_discovery_exhaustion_records_source_evidence(tmp_path):
    root_hash = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:16]
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(json.dumps({
        "schema_version": 1,
        "root_sha256_prefix": root_hash,
        "repositories": [],
    }), encoding="utf-8")
    ticks = iter((0.0, 0.005))
    budget = WorkBudget.start(5, clock=lambda: next(ticks))
    result = resolve_scope(RouteRequest.create(tmp_path, freshness="strict"), budget)
    assert result.complete is False
    assert result.source["validation"] == "UNKNOWN"
    assert result.source["omissions"] == [{
        "reason_code": "budget-exhausted",
        "rule_ref": "route.strict.discovery",
        "boundary": "scan.directory",
    }]


def test_max_repos_omits_with_receipts(tmp_path):
    for rel in ("public/a", "public/b", "public/c"):
        _repo(tmp_path, rel)
    request = RouteRequest.create(
        tmp_path,
        paths=["public/c", "public/b", "public/a"],
        max_repos=1,
    )
    budget = WorkBudget.start(5000)
    result = resolve_scope(request, budget)
    assert len(result.selected) == 1
    assert len(result.omitted) == 2
    assert {item["reason_code"] for item in result.omitted} == {"max-repos"}
    assert result.reconciliation["verdict"] == "MATCH"
    assert budget.counters["repositories_visited"] == 1
