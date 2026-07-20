import json
import os
from copy import deepcopy
from pathlib import Path
from time import time

import index_graph.route.freshness as freshness_module
import pytest
from index_graph.freshness import repo_fingerprint
from index_graph.route.budget import WorkBudget
from index_graph.route.cache import RouteCache, cache_identity
from index_graph.route.freshness import build_manifest, validate_manifest
from index_graph.route.model import ROUTE_SCHEMA, RouteRequest
from index_graph.route.scope import RepoCandidate


def _scope(root):
    repo = root / "public/index"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src/mod.py").write_text("x = 1\n", encoding="utf-8")
    return [RepoCandidate("public/index", repo, "public/index", "explicit")]


def _snapshot(kind="explicit", candidates=("public/index",), complete=True):
    return {
        "kind": kind,
        "candidate_ids": list(candidates),
        "complete": complete,
        "map": None,
    }


def _reconciliation(count=1):
    return {
        "verdict": "MATCH",
        "counts": {
            "candidates": count,
            "selected": count,
            "rejected": 0,
            "omitted": 0,
        },
        "failures": [],
    }


def _receipt(verdict="MATCH"):
    return {
        "schema": ROUTE_SCHEMA,
        "verdict": verdict,
        "root": ".",
        "query": "",
        "freshness": {
            "mode": "bounded",
            "validation": "BUILT",
            "cache_age_ms": None,
            "source_signature": None,
            "recursive_complete": True,
        },
        "budget": {
            "requested_ms": 5000,
            "elapsed_ms": 1,
            "repositories_visited": 1,
            "directories_visited": 2,
            "candidate_documents_observed": 0,
            "document_bodies_opened": 0,
            "files_validated": 1,
            "exhausted_at": None,
        },
        "scope": {
            "paths": ["public/index"],
            "max_repos": 12,
            "max_docs": 8,
            "budget_ms": 5000,
            "complete": True,
            "documents_complete": True,
            "graph_complete": True,
            "manifest_complete": True,
        },
        "selection": {
            "candidates": ["public/index"],
            "selected": ["public/index"],
            "rejected": [],
            "omitted": [],
        },
        "documents": {
            "selected": [],
            "rejected": [],
            "omitted": [],
            "reconciliation": _reconciliation(0),
        },
        "evidence": {"router_pack": {}},
        "reconciliation": _reconciliation(),
        "recheck": {
            "cli": "index route --root . --path public/index",
            "mcp": "index.route",
        },
    }


def test_cache_identity_does_not_walk_workspace(tmp_path, monkeypatch):
    request = RouteRequest.create(tmp_path, paths=["public/index"])
    monkeypatch.setattr(os, "walk", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("cache identity must not walk")
    ))
    assert cache_identity(tmp_path, request) == cache_identity(tmp_path, request)
    tighter = RouteRequest.create(
        tmp_path, paths=["public/index"], budget_ms=request.budget_ms - 1
    )
    assert cache_identity(tmp_path, request) != cache_identity(tmp_path, tighter)


def test_strict_manifest_detects_same_metadata_edit_and_nested_addition(tmp_path):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    assert manifest["graph_signatures"]["public/index"] == repo_fingerprint(
        scope[0].path
    )
    file = scope[0].path / "src/mod.py"
    before = file.stat()
    file.write_text("y = 1\n", encoding="utf-8")
    os.utime(file, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    (scope[0].path / "src/new.py").write_text("y = 1\n", encoding="utf-8")
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_strict_manifest_detects_same_metadata_markdown_edit(tmp_path):
    scope = _scope(tmp_path)
    readme = scope[0].path / "README.md"
    readme.write_text("# Alpha\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
        document_bodies={"public/index/README.md": "# Alpha\n"},
    )
    before = readme.stat()
    readme.write_text("# Bravo\n", encoding="utf-8")
    os.utime(readme, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_strict_manifest_tracks_markdown_paths_without_opening_new_body(tmp_path):
    scope = _scope(tmp_path)
    first_budget = WorkBudget.start(5000)
    before = build_manifest(
        tmp_path,
        scope,
        first_budget,
        scope_snapshot=_snapshot(),
        strict=True,
    )
    (scope[0].path / "docs").mkdir()
    (scope[0].path / "docs/new.md").write_text("# New\n", encoding="utf-8")
    second_budget = WorkBudget.start(5000)
    after = build_manifest(
        tmp_path,
        scope,
        second_budget,
        scope_snapshot=_snapshot(),
        strict=True,
    )
    assert after["markdown_paths_signature"] != before["markdown_paths_signature"]
    assert second_budget.counters["document_bodies_opened"] == 0


def test_manifest_validation_uses_stats_not_recursive_walk(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    monkeypatch.setattr(os, "walk", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("hot validation must not walk")
    ))
    budget = WorkBudget.start(5000)
    assert validate_manifest(tmp_path, manifest, budget, strict=False)[
        "status"
    ] == "FRESH"
    assert budget.counters["directories_visited"] == len(manifest["directories"])
    assert budget.counters["files_validated"] == len(manifest["files"])


def test_manifest_budget_interruption_reports_exact_unchecked_counts(tmp_path):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    readings = iter((0.0, 2.0))
    result = validate_manifest(
        tmp_path,
        manifest,
        WorkBudget.start(1000, clock=lambda: next(readings)),
        strict=False,
    )
    assert result == {
        "status": "UNKNOWN",
        "checked": {"directories": 0, "files": 0, "documents": 0},
        "unchecked": {
            "directories": len(manifest["directories"]),
            "files": len(manifest["files"]),
            "documents": len(manifest["document_digests"]),
        },
        "exhausted_at": "manifest.directory",
    }


def test_strict_budget_interruption_reports_scanned_prefix(tmp_path):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    readings = iter((0.0, 0.0, 0.0, 2.0))
    result = validate_manifest(
        tmp_path,
        manifest,
        WorkBudget.start(1000, clock=lambda: next(readings)),
        strict=True,
    )
    assert result["status"] == "UNKNOWN"
    assert result["checked"] == {
        "directories": len(manifest["directories"]),
        "files": 0,
        "documents": 0,
    }
    assert result["unchecked"] == {
        "directories": 0,
        "files": len(manifest["files"]),
        "documents": 0,
    }


def test_strict_manifest_detects_removed_empty_repository(tmp_path):
    repo = tmp_path / "empty"
    (repo / ".git").mkdir(parents=True)
    scope = [RepoCandidate("empty", repo, "empty", "explicit")]
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(candidates=("empty",)),
        strict=True,
    )
    (repo / ".git").rmdir()
    repo.rmdir()
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_strict_manifest_never_opens_unselected_document(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    outside = tmp_path / "private.md"
    outside.write_text("secret", encoding="utf-8")
    manifest["document_digests"]["private.md"] = "not-a-real-digest"
    original = Path.read_text

    def guarded_read(path, *args, **kwargs):
        if path == outside:
            raise AssertionError("strict validation opened an unselected body")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_strict_document_interruption_uses_docs_open_boundary(tmp_path):
    scope = _scope(tmp_path)
    readme = scope[0].path / "README.md"
    readme.write_text("# Alpha\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
        document_bodies={"public/index/README.md": "# Alpha\n"},
    )
    readings = iter((0.0, 0.0, 0.0, 0.0, 0.0, 2.0))
    budget = WorkBudget.start(1000, clock=lambda: next(readings))
    result = validate_manifest(tmp_path, manifest, budget, strict=True)
    assert result["status"] == "UNKNOWN"
    assert result["exhausted_at"] == "docs.open"
    assert result["unchecked"]["documents"] == 1


def _assert_unknown_evidence(result, *, boundary):
    assert result["status"] == "UNKNOWN"
    assert result["boundary"] == boundary
    assert result["reason"] == "unreadable"
    assert all(value >= 0 for value in result["checked"].values())
    assert all(value >= 0 for value in result["unchecked"].values())


def test_unreadable_config_identity_is_unknown(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    config = tmp_path / ".index.toml"
    config.write_text("[scan]\njobs=1\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    original = Path.read_bytes

    def denied(path):
        if path == config:
            raise PermissionError("denied")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", denied)
    _assert_unknown_evidence(
        validate_manifest(
            tmp_path, manifest, WorkBudget.start(5000), strict=True
        ),
        boundary="freshness.config",
    )


def test_unreadable_workspace_map_identity_is_unknown(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    workspace_map = tmp_path / "WORKSPACE-REPO-MAP.json"
    workspace_map.write_text('{"schema_version":1}', encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(kind="workspace-map"),
        strict=True,
    )
    original = Path.read_bytes

    def denied(path):
        if path == workspace_map:
            raise PermissionError("denied")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", denied)
    _assert_unknown_evidence(
        validate_manifest(
            tmp_path, manifest, WorkBudget.start(5000), strict=True
        ),
        boundary="freshness.workspace-map",
    )


def test_strict_walk_permission_error_is_unknown(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )

    def denied_walk(_root, *, onerror):
        onerror(PermissionError("denied"))
        return iter(())

    monkeypatch.setattr(freshness_module.os, "walk", denied_walk)
    _assert_unknown_evidence(
        validate_manifest(
            tmp_path, manifest, WorkBudget.start(5000), strict=True
        ),
        boundary="manifest.walk",
    )


def test_strict_repository_stat_permission_error_is_unknown(
    tmp_path, monkeypatch
):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    repository = scope[0].path
    original = Path.stat

    def denied(path, *args, **kwargs):
        if path == repository:
            raise PermissionError("denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", denied)
    _assert_unknown_evidence(
        validate_manifest(
            tmp_path, manifest, WorkBudget.start(5000), strict=True
        ),
        boundary="manifest.repository",
    )


def test_strict_walk_missing_subtree_is_drift(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )

    def missing_walk(_root, *, onerror):
        onerror(FileNotFoundError("removed"))
        return iter(())

    monkeypatch.setattr(freshness_module.os, "walk", missing_walk)
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_strict_relevant_file_permission_error_is_unknown(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    source = scope[0].path / "src/mod.py"
    original = Path.read_bytes

    def denied(path):
        if path == source:
            raise PermissionError("denied")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", denied)
    _assert_unknown_evidence(
        validate_manifest(
            tmp_path, manifest, WorkBudget.start(5000), strict=True
        ),
        boundary="manifest.content",
    )


def test_unreadable_build_never_emits_complete_graph_signature(
    tmp_path, monkeypatch
):
    scope = _scope(tmp_path)
    source = scope[0].path / "src/mod.py"
    original = Path.read_bytes

    def denied(path):
        if path == source:
            raise PermissionError("denied")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", denied)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    assert manifest["complete"] is False
    assert manifest["graph_signatures"]["public/index"] is None
    assert manifest["strict_signature"] is None


def test_strict_document_permission_error_is_unknown(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    readme = scope[0].path / "README.md"
    readme.write_text("# Alpha\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
        document_bodies={"public/index/README.md": "# Alpha\n"},
    )
    original = Path.read_text

    def denied(path, *args, **kwargs):
        if path == readme:
            raise PermissionError("denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    _assert_unknown_evidence(
        validate_manifest(
            tmp_path, manifest, WorkBudget.start(5000), strict=True
        ),
        boundary="docs.open",
    )


def test_strict_document_encoding_error_is_unknown(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    readme = scope[0].path / "README.md"
    readme.write_text("# Alpha\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
        document_bodies={"public/index/README.md": "# Alpha\n"},
    )
    original = Path.read_text

    def invalid(path, *args, **kwargs):
        if path == readme:
            raise UnicodeError("invalid UTF-8")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", invalid)
    _assert_unknown_evidence(
        validate_manifest(
            tmp_path, manifest, WorkBudget.start(5000), strict=True
        ),
        boundary="docs.open",
    )


def test_strict_document_invalid_utf8_is_unknown(tmp_path):
    scope = _scope(tmp_path)
    readme = scope[0].path / "README.md"
    readme.write_text("# Alpha\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
        document_bodies={"public/index/README.md": "# Alpha\n"},
    )
    readme.write_bytes(b"\xff\xfe")
    _assert_unknown_evidence(
        validate_manifest(
            tmp_path, manifest, WorkBudget.start(5000), strict=True
        ),
        boundary="docs.open",
    )


def test_bounded_manifest_does_not_create_unvalidated_document_evidence(tmp_path):
    scope = _scope(tmp_path)
    readme = scope[0].path / "README.md"
    readme.write_text("# Alpha\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
        document_bodies={"public/index/README.md": "# Alpha\n"},
    )
    assert manifest["document_digests"] == {}
    result = validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=False
    )
    assert result["status"] == "FRESH"
    assert result["unchecked"]["documents"] == 0


def test_workspace_derived_manifest_detects_new_sibling_repository(tmp_path):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(kind="discovery"),
        strict=True,
    )
    sibling = tmp_path / "public/forum"
    (sibling / ".git").mkdir(parents=True)
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "DRIFT"


def test_unreadable_candidate_universe_is_unknown(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(kind="discovery"),
        strict=True,
    )

    def incomplete_discovery(
        root, config, *, skipped, checkpoint, prune_repo_contents
    ):
        skipped.append(root / "unreadable")
        return [scope[0].path]

    monkeypatch.setattr(
        freshness_module, "discover_repos", incomplete_discovery
    )
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "UNKNOWN"


def test_strict_validation_rejects_incomplete_map_universe(tmp_path):
    scope = _scope(tmp_path)
    (tmp_path / "WORKSPACE-REPO-MAP.json").write_text(
        '{"schema_version":1}', encoding="utf-8"
    )
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(kind="workspace-map", complete=False),
        strict=True,
    )
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=True
    )["status"] == "UNKNOWN"
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=False
    )["status"] == "FRESH"


def test_route_cache_ignores_corrupt_entry(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    key = "abc"
    cache.clear_memory()
    cache.path_for(key).parent.mkdir(parents=True)
    cache.path_for(key).write_bytes(b"{not-json")
    assert cache.get(key) is None


def test_route_cache_ignores_incompatible_nested_schema(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    key = "incompatible"
    cache.clear_memory()
    cache.path_for(key).parent.mkdir(parents=True)
    cache.path_for(key).write_text(json.dumps({
        "schema": "index.route-cache-entry/v1",
        "payload": {"schema": "index.route-receipt/v0"},
        "manifest": {"schema": "index.route-manifest/v1"},
        "markdown": "",
    }), encoding="utf-8")
    assert cache.get(key) is None


def test_route_cache_ignores_malformed_nested_types(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    key = "malformed"
    cache.path_for(key).parent.mkdir(parents=True)
    cache.path_for(key).write_text(json.dumps({
        "schema": "index.route-cache-entry/v1",
        "payload": [],
        "manifest": {"schema": "index.route-manifest/v1"},
        "markdown": "",
    }), encoding="utf-8")
    assert cache.get(key) is None


def test_route_cache_ignores_malformed_manifest_collections(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    key = "malformed-manifest"
    cache.path_for(key).parent.mkdir(parents=True)
    cache.path_for(key).write_text(json.dumps({
        "schema": "index.route-cache-entry/v1",
        "created_at": time(),
        "payload": {"schema": ROUTE_SCHEMA},
        "manifest": {
            "schema": "index.route-manifest/v1",
            "complete": True,
            "directories": 3,
        },
        "markdown": "",
    }), encoding="utf-8")
    assert cache.get(key) is None


def test_route_cache_rejects_schema_only_receipt(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    cache.put(
        "schema-only",
        payload={"schema": ROUTE_SCHEMA},
        markdown="",
        manifest=manifest,
    )
    assert cache.get("schema-only") is None


def test_route_cache_rejects_malformed_reconciliation(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    payload = _receipt()
    payload["reconciliation"]["counts"]["selected"] = "one"
    cache.put(
        "bad-reconciliation",
        payload=payload,
        markdown="",
        manifest=manifest,
    )
    assert cache.get("bad-reconciliation") is None


def test_route_cache_accepts_ranked_receipt_and_root_selection_item(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(
            candidates=(".", "public/index")
        ),
        strict=False,
    )
    payload = _receipt("PARTIAL")
    payload["selection"]["candidates"] = ["public/index", "."]
    payload["selection"]["omitted"] = [{
        "path": ".",
        "reason_code": "max-repos",
        "rule_ref": "route.max_repos:1",
        "evidence": {},
    }]
    payload["documents"]["selected"] = [
        "public/index/z.md",
        "public/index/a.md",
    ]
    payload["documents"]["reconciliation"] = _reconciliation(2)
    payload["reconciliation"] = {
        "verdict": "MATCH",
        "counts": {
            "candidates": 2,
            "selected": 1,
            "rejected": 0,
            "omitted": 1,
        },
        "failures": [],
    }
    cache.put(
        "ranked-receipt",
        payload=payload,
        markdown="",
        manifest=manifest,
    )
    assert cache.get("ranked-receipt") is not None


def test_route_cache_rejects_semantically_corrupt_match(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    payload = _receipt("MATCH")
    payload["scope"]["complete"] = False
    payload["reconciliation"]["counts"]["selected"] = 0
    cache.put(
        "corrupt-match",
        payload=payload,
        markdown="",
        manifest=manifest,
    )
    assert cache.get("corrupt-match") is None


def test_route_cache_rejects_duplicate_document_items(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    item = {
        "path": "public/index/README.md",
        "reason_code": "max-docs",
        "rule_ref": "route.docs.max-docs",
        "evidence": {},
    }
    payload = _receipt("PARTIAL")
    payload["documents"]["omitted"] = [item, deepcopy(item)]
    cache.put(
        "duplicate-doc-items",
        payload=payload,
        markdown="",
        manifest=manifest,
    )
    assert cache.get("duplicate-doc-items") is None


def test_route_cache_rejects_match_with_incomplete_manifest(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    manifest["complete"] = False
    cache.put(
        "incomplete-match",
        payload=_receipt("MATCH"),
        markdown="",
        manifest=manifest,
    )
    assert cache.get("incomplete-match") is None


def test_route_cache_only_reuses_incomplete_map_as_partial(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    workspace_map = tmp_path / "WORKSPACE-REPO-MAP.json"
    workspace_map.write_text('{"schema_version":1}', encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(kind="workspace-map", complete=False),
        strict=False,
    )
    match = _receipt("MATCH")
    cache.put(
        "map-match", payload=match, markdown="", manifest=manifest
    )
    assert cache.get("map-match") is None
    partial = deepcopy(match)
    partial["verdict"] = "PARTIAL"
    cache.put(
        "map-partial", payload=partial, markdown="", manifest=manifest
    )
    assert cache.get("map-partial") is not None


def test_route_cache_allows_redacted_nonfilesystem_candidate_id(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    redacted = "outside-root:0123456789abcdef"
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(
            candidates=(redacted, "public/index")
        ),
        strict=False,
    )
    payload = _receipt("PARTIAL")
    payload["selection"]["candidates"] = [redacted, "public/index"]
    payload["selection"]["rejected"] = [{
        "path": redacted,
        "reason_code": "outside-root",
        "rule_ref": "route.explicit.root",
        "evidence": {},
    }]
    payload["reconciliation"] = {
        "verdict": "MATCH",
        "counts": {
            "candidates": 2,
            "selected": 1,
            "rejected": 1,
            "omitted": 0,
        },
        "failures": [],
    }
    cache.put(
        "redacted-candidate",
        payload=payload,
        markdown="",
        manifest=manifest,
    )
    assert cache.get("redacted-candidate") is not None


def test_overlapping_repositories_emit_unique_sorted_stat_evidence(tmp_path):
    parent = _scope(tmp_path)[0]
    nested = parent.path / "nested"
    (nested / ".git").mkdir(parents=True)
    (nested / "nested.py").write_text("x = 1\n", encoding="utf-8")
    repositories = [
        parent,
        RepoCandidate(
            "public/index/nested",
            nested,
            "public/index/nested",
            "explicit",
        ),
    ]
    manifest = build_manifest(
        tmp_path,
        repositories,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(
            candidates=("public/index", "public/index/nested")
        ),
        strict=True,
    )
    for field in ("directories", "files"):
        paths = [record["path"] for record in manifest[field]]
        assert paths == sorted(set(paths))


def test_ranked_repositories_emit_canonical_manifest_and_cache(tmp_path):
    repositories = []
    for rel_path in ("public/zeta", "public/alpha"):
        repo = tmp_path / rel_path
        (repo / ".git").mkdir(parents=True)
        (repo / "mod.py").write_text("x = 1\n", encoding="utf-8")
        repositories.append(
            RepoCandidate(rel_path, repo, rel_path, "explicit")
        )
    manifest = build_manifest(
        tmp_path,
        repositories,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(
            candidates=("public/zeta", "public/alpha")
        ),
        strict=False,
    )
    assert manifest["repositories"] == ["public/alpha", "public/zeta"]
    assert manifest["scope_snapshot"]["candidate_ids"] == [
        "public/alpha", "public/zeta",
    ]
    assert list(manifest["graph_signatures"]) == [
        "public/alpha", "public/zeta",
    ]
    payload = _receipt()
    payload["scope"]["paths"] = ["public/zeta", "public/alpha"]
    payload["selection"]["candidates"] = ["public/zeta", "public/alpha"]
    payload["selection"]["selected"] = ["public/zeta", "public/alpha"]
    payload["reconciliation"] = _reconciliation(2)
    cache = RouteCache(tmp_path / "cache")
    cache.put(
        "ranked-manifest",
        payload=payload,
        markdown="",
        manifest=manifest,
    )
    entry = cache.get("ranked-manifest")
    assert entry is not None
    assert entry["payload"]["selection"]["selected"] == [
        "public/zeta", "public/alpha",
    ]


def test_strict_partial_accepts_matching_null_signatures(tmp_path):
    scope = _scope(tmp_path)
    readings = iter((0.0, 2.0))
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(1000, clock=lambda: next(readings)),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    assert manifest["complete"] is False
    assert manifest["strict_signature"] is None
    payload = _receipt("PARTIAL")
    payload["freshness"].update({
        "mode": "strict",
        "source_signature": None,
        "recursive_complete": False,
    })
    for key in list(payload["scope"]):
        if key.endswith("complete"):
            payload["scope"][key] = False
    cache = RouteCache(tmp_path / "cache")
    cache.put(
        "strict-partial",
        payload=payload,
        markdown="",
        manifest=manifest,
    )
    assert cache.get("strict-partial") is not None


def test_missing_nullable_manifest_signature_is_cache_miss(tmp_path):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=True,
    )
    manifest.pop("strict_signature")
    payload = _receipt("PARTIAL")
    payload["freshness"].update({
        "mode": "strict",
        "source_signature": None,
        "recursive_complete": False,
    })
    cache = RouteCache(tmp_path / "cache")
    cache.put(
        "missing-signature",
        payload=payload,
        markdown="",
        manifest=manifest,
    )
    assert cache.get("missing-signature") is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "../private"),
        ("candidate", "C:\\private"),
        ("document", "/private.md"),
        ("graph", "public//index"),
        ("map", "../WORKSPACE-REPO-MAP.json"),
        ("stat", "public/index/../private"),
    ],
)
def test_route_cache_rejects_nonportable_manifest_paths(
    tmp_path, field, value
):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    if field == "repository":
        manifest["repositories"][0] = value
    elif field == "candidate":
        manifest["scope_snapshot"]["candidate_ids"][0] = value
    elif field == "document":
        manifest["document_digests"][value] = "a" * 64
    elif field == "graph":
        manifest["graph_signatures"] = {value: None}
    elif field == "map":
        manifest["scope_snapshot"]["map"] = {
            "path": value,
            "sha256": "a" * 64,
        }
    else:
        manifest["directories"][0]["path"] = value
    cache.put(
        f"bad-{field}", payload=_receipt(), markdown="", manifest=manifest
    )
    assert cache.get(f"bad-{field}") is None


def test_route_cache_rejects_duplicate_manifest_evidence(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    manifest["directories"].append(deepcopy(manifest["directories"][0]))
    cache.put(
        "duplicate-evidence",
        payload=_receipt(),
        markdown="",
        manifest=manifest,
    )
    assert cache.get("duplicate-evidence") is None


def test_route_cache_rejects_unsorted_manifest_evidence(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    scope = _scope(tmp_path)
    readme = scope[0].path / "README.md"
    readme.write_text("# Index\n", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    manifest["files"].reverse()
    cache.put(
        "unsorted-evidence",
        payload=_receipt(),
        markdown="",
        manifest=manifest,
    )
    assert cache.get("unsorted-evidence") is None


def test_validate_manifest_rejects_traversal_before_stat(tmp_path, monkeypatch):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    manifest["files"][0]["path"] = "../private"
    original = Path.stat

    def guarded(path, *args, **kwargs):
        if ".." in path.parts:
            raise AssertionError("manifest traversal escaped root")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", guarded)
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=False
    )["status"] == "DRIFT"


def test_validate_manifest_rejects_malformed_path_types(tmp_path):
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    manifest["repositories"] = [None, "public/index"]
    assert validate_manifest(
        tmp_path, manifest, WorkBudget.start(5000), strict=False
    )["status"] == "DRIFT"


def test_route_cache_memory_is_namespaced_by_directory(tmp_path):
    first = RouteCache(tmp_path / "first")
    second = RouteCache(tmp_path / "second")
    first.clear_memory()
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    first.put(
        "shared-key", payload=_receipt(), markdown="first", manifest=manifest
    )
    assert second.get("shared-key") is None


def test_route_cache_returns_deep_copies(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    cache.clear_memory()
    payload = _receipt()
    scope = _scope(tmp_path)
    manifest = build_manifest(
        tmp_path,
        scope,
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(),
        strict=False,
    )
    cache.put("copies", payload=payload, markdown="ok", manifest=manifest)
    first = cache.get("copies")
    assert first is not None
    first["payload"]["selection"]["selected"][0] = "mutated"
    second = cache.get("copies")
    assert second is not None
    assert second["payload"]["selection"]["selected"][0] == "public/index"


def test_route_cache_validates_memory_entries(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    cache.clear_memory()
    cache.put(
        "invalid-memory",
        payload={"schema": "index.route-receipt/v0"},
        markdown="",
        manifest={"schema": "index.route-manifest/v1"},
    )
    assert cache.get("invalid-memory") is None


def test_route_cache_uses_unique_sibling_temporary_file(tmp_path, monkeypatch):
    cache = RouteCache(tmp_path / "cache")
    manifest = build_manifest(
        tmp_path,
        [],
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(candidates=()),
        strict=False,
    )
    monkeypatch.setattr(
        Path,
        "with_suffix",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("fixed temporary path is not concurrency safe")
        ),
    )
    cache.put(
        "atomic",
        payload={"schema": ROUTE_SCHEMA},
        markdown="",
        manifest=manifest,
    )
    assert cache.path_for("atomic").is_file()
