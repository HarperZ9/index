import json
import os
from pathlib import Path
from time import time

import index_graph.route.freshness as freshness_module
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


def test_route_cache_returns_deep_copies(tmp_path):
    cache = RouteCache(tmp_path / "cache")
    cache.clear_memory()
    payload = {"schema": ROUTE_SCHEMA, "selected": [{"path": "public/index"}]}
    manifest = build_manifest(
        tmp_path,
        [],
        WorkBudget.start(5000),
        scope_snapshot=_snapshot(candidates=()),
        strict=False,
    )
    cache.put("copies", payload=payload, markdown="ok", manifest=manifest)
    first = cache.get("copies")
    assert first is not None
    first["payload"]["selected"][0]["path"] = "mutated"
    second = cache.get("copies")
    assert second is not None
    assert second["payload"]["selected"][0]["path"] == "public/index"


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
