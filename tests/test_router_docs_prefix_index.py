from __future__ import annotations

import json

from index_graph.graph.build import DependencyGraph, RepoNode, build_graph
from index_graph.knowledge.docs import Doc
import index_graph.knowledge.atlas as atlas
from index_graph import router_jobs


def _graph(*names: str) -> DependencyGraph:
    repos = tuple(
        RepoNode(name, f"/workspace/{name}", (), frozenset(), "d", frozenset())
        for name in names
    )
    return DependencyGraph(repos, (), {name: ("library",) for name in names}, ())


def _expected_describes(docs: list[Doc], repo_dirs: dict[str, str]) -> list[dict]:
    edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for doc in docs:
        best: str | None = None
        best_len = -1
        for repo, repo_dir in repo_dirs.items():
            contains = doc.dir_rel == repo_dir or (
                repo_dir != "" and doc.dir_rel.startswith(repo_dir + "/")
            )
            if contains and len(repo_dir) > best_len:
                best, best_len = repo, len(repo_dir)
        if best is None:
            continue
        key = (doc.rel_path, "repo", best)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"type": "describes", "from": doc.rel_path, "to": best, "to_kind": "repo"})
    return sorted(edges, key=lambda e: (e["from"], e["type"], e["to_kind"], e["to"]))


def test_indexed_describes_matches_current_nested_prefix_and_case_semantics():
    # Catches an indexed matcher that treats path prefixes as plain strings,
    # folds case on Windows, or lets a root repo describe nested docs.
    repo_dirs = {
        "root": "",
        "app": "apps/app",
        "app-lib": "apps/app-lib",
        "nested": "apps/app/packages/nested",
        "case": "Case/Repo",
        "case-lower": "case/repo",
    }
    docs = [
        Doc("README.md", "Root", "", (), ""),
        Doc("apps/app/README.md", "App", "", (), "apps/app"),
        Doc("apps/app/docs/guide.md", "Guide", "", (), "apps/app/docs"),
        Doc("apps/app-lib/README.md", "Lib", "", (), "apps/app-lib"),
        Doc("apps/application/README.md", "Prefix", "", (), "apps/application"),
        Doc("apps/app/packages/nested/readme.md", "Nested", "", (), "apps/app/packages/nested"),
        Doc("Case/Repo/README.md", "Case", "", (), "Case/Repo"),
        Doc("case/repo/README.md", "Lower", "", (), "case/repo"),
        Doc("Case/RepoExtra/README.md", "Sibling", "", (), "Case/RepoExtra"),
    ]

    assert atlas._describes_edges_indexed(docs, repo_dirs) == _expected_describes(docs, repo_dirs)


def test_indexed_describes_preserves_duplicate_doc_multiplicity_and_ordering():
    # Catches deduping by repo, relying on discovery order, or applying max_docs
    # before the full describes edge set is built.
    repo_dirs = {"repo": "repo"}
    docs = [
        Doc(f"repo/docs/{i:03}.md", f"D{i}", "", (), "repo/docs")
        for i in reversed(range(80))
    ]
    want = _expected_describes(docs, repo_dirs)

    got = atlas._describes_edges_indexed(docs, repo_dirs)

    assert len(got) == 80
    assert got == want
    assert got[0]["from"] == "repo/docs/000.md"
    assert got[-1]["from"] == "repo/docs/079.md"


def test_indexed_describes_matches_current_no_docs_and_mixed_path_strings():
    # Catches normalizing separators beyond the current string contract. The
    # current matcher treats "/" as the only containment separator but still
    # allows exact matches for other path strings already supplied by callers.
    assert atlas._describes_edges_indexed([], {"repo": "repo"}) == []
    repo_dirs = {
        "win-root": "apps\\win",
        "win-child": "apps\\win/child",
        "posix": "apps/win",
    }
    docs = [
        Doc("apps\\win\\README.md", "Exact windows string", "", (), "apps\\win"),
        Doc("apps\\win\\child\\README.md", "Backslash child", "", (), "apps\\win\\child"),
        Doc("apps\\win/child/README.md", "Mixed child", "", (), "apps\\win/child"),
        Doc("apps/win/README.md", "Posix", "", (), "apps/win"),
        Doc("apps/win-extra/README.md", "Prefix collision", "", (), "apps/win-extra"),
    ]

    assert atlas._describes_edges_indexed(docs, repo_dirs) == _expected_describes(docs, repo_dirs)


def test_router_job_records_private_phase_timings_and_cache_summary(tmp_path, monkeypatch):
    # Catches successful jobs that expose only coarse progress, leaving docs and
    # cache bottlenecks indistinguishable after completion.
    workspace = tmp_path / "workspace"
    repo = workspace / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='repo'\nversion='0'\n", encoding="utf-8")
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    job_root = tmp_path / "jobs"
    monkeypatch.setenv("INDEX_ROUTER_JOB_DIR", str(job_root))

    job = router_jobs.create_router_job(workspace, job_root=job_root, max_docs=10)
    assert router_jobs.run_router_job_worker(job["job_dir"]) == 0

    status = router_jobs.read_router_job_status(job["job_id"], job_root=job_root)
    timings = status.get("phase_timings_ms")
    assert isinstance(timings, dict)
    for key in ["repo_discovery", "graph", "router_docs", "router_pack", "render", "result_write"]:
        assert isinstance(timings.get(key), int)
        assert timings[key] >= 0
    cache = status.get("graph_cache")
    assert isinstance(cache, dict)
    assert set(cache) >= {"hits", "misses", "writes", "invalid", "bypassed"}
    assert sum(int(cache[key]) for key in ["hits", "misses", "invalid", "bypassed"]) == 1
    stage_timings = cache.get("stage_timings_ms")
    assert isinstance(stage_timings, dict)
    for key in ["fingerprint", "cache_read", "cache_decode", "cache_rehydrate", "fresh_build", "cache_write"]:
        assert isinstance(stage_timings.get(key), int)
        assert stage_timings[key] >= 0
    fingerprint = cache.get("fingerprint")
    assert isinstance(fingerprint, dict)
    assert isinstance(fingerprint.get("files"), int)
    assert isinstance(fingerprint.get("bytes"), int)
    docs_detail = status.get("router_docs")
    assert isinstance(docs_detail, dict)
    assert docs_detail.get("docs") == 1
    for key in ["traversal_ms", "row_construction_ms"]:
        assert isinstance(docs_detail.get(key), int)
        assert docs_detail[key] >= 0

    events = [
        json.loads(line)
        for line in (tmp_path / "jobs" / job["job_id"] / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    timing_events = [event for event in events if event.get("phase") == "timing"]
    assert {event.get("step") for event in timing_events} >= {
        "repo_discovery", "graph", "router_docs", "router_pack", "render", "result_write"
    }
    assert all("content" not in event and "repo_path" not in event for event in timing_events)


def test_graph_cache_summary_counts_hit_miss_bypass_and_invalid(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    repo = workspace / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='repo'\nversion='0'\n", encoding="utf-8")
    (repo / "README.md").write_text("Repo description\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(cache_dir))
    paths = {"repo": repo}

    cold = build_graph(paths, jobs=1).cache_summary
    assert cold is not None
    assert cold["hits"] == 0
    assert cold["misses"] == 1
    assert cold["writes"] == 1
    assert cold["reasons"] == {"not_found": 1}

    warm = build_graph(paths, jobs=1).cache_summary
    assert warm is not None
    assert warm["hits"] == 1
    assert warm["misses"] == 0
    assert warm["writes"] == 0
    assert warm["reasons"] == {"hit": 1}

    bypassed = build_graph(paths, jobs=1, use_cache=False).cache_summary
    assert bypassed is not None
    assert bypassed["bypassed"] == 1
    assert bypassed["writes"] == 0
    assert bypassed["reasons"] == {"disabled_or_unsupported": 1}

    for cache_file in cache_dir.glob("*.json"):
        cache_file.write_text("{bad json", encoding="utf-8")
    invalid = build_graph(paths, jobs=1).cache_summary
    assert invalid is not None
    assert invalid["invalid"] == 1
    assert invalid["writes"] == 1
    assert invalid["reasons"] == {"invalid_json": 1}


def test_warm_hit_reports_source_fingerprint_cost_without_rebuilding(tmp_path, monkeypatch):
    # Catches treating a cache hit as free, which hides exact-byte source
    # fingerprint cost and makes warm-run performance diagnosis impossible.
    workspace = tmp_path / "workspace"
    repo = workspace / "repo"
    (repo / ".git").mkdir(parents=True)
    manifest = "[project]\nname='repo'\nversion='0'\n"
    (repo / "pyproject.toml").write_text(manifest, encoding="utf-8")
    (repo / "README.md").write_text("Repo description\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    paths = {"repo": repo}

    build_graph(paths, jobs=1)
    warm = build_graph(paths, jobs=1)

    cache = warm.cache_summary
    assert cache is not None
    assert cache["hits"] == 1
    assert cache["misses"] == 0
    assert cache["writes"] == 0
    stage_timings = cache.get("stage_timings_ms")
    assert isinstance(stage_timings, dict)
    assert stage_timings["fingerprint"] >= 0
    assert stage_timings["cache_read"] >= 0
    assert stage_timings["cache_decode"] >= 0
    assert stage_timings["cache_rehydrate"] >= 0
    assert stage_timings["fresh_build"] == 0
    assert stage_timings["cache_write"] == 0
    fingerprint = cache.get("fingerprint")
    assert isinstance(fingerprint, dict)
    assert fingerprint["files"] >= 1
    assert fingerprint["bytes"] >= len(manifest.encode("utf-8"))


def test_single_source_byte_mutation_causes_one_miss_and_preserves_graph(tmp_path, monkeypatch):
    # Catches weakening exact-byte freshness to metadata-only checks: a
    # graph-neutral source byte edit must miss the cache while preserving graph
    # facts, edge order, and equality semantics.
    workspace = tmp_path / "workspace"
    repo = workspace / "repo"
    (repo / ".git").mkdir(parents=True)
    manifest = repo / "pyproject.toml"
    manifest.write_text("[project]\nname='repo'\nversion='0'\n", encoding="utf-8")
    (repo / "README.md").write_text("Repo description\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    paths = {"repo": repo}

    cold = build_graph(paths, jobs=1)
    warm = build_graph(paths, jobs=1)
    manifest.write_text("[project]\nname='repo'\nversion='0'\n# graph-neutral byte edit\n", encoding="utf-8")
    changed = build_graph(paths, jobs=1)

    assert cold == warm == changed
    assert warm.edges == changed.edges
    assert warm.repos == changed.repos
    cache = changed.cache_summary
    assert cache is not None
    assert cache["hits"] == 0
    assert cache["misses"] == 1
    assert cache["writes"] == 1
    assert cache["reasons"] == {"not_found": 1}
