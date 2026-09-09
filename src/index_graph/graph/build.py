"""Assemble repo trees + resolvers into a DependencyGraph."""
from __future__ import annotations

import configparser
import json
import os
import tomllib
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import perf_counter

from . import cache as _cache
from .edges import Edge, build_index, resolve_edges
from .description import description as _description
from .walk import cached_file_scope, read_source_text, source_reuse_complete, walk_files
from .resolvers import ALL_RESOLVERS
from .resolvers.base import RawEdge
from .roles import derive_roles

make_lookup = _cache.make_lookup

@dataclass(frozen=True)
class RepoNode:
    name: str
    path: str
    ecosystems: tuple[str, ...]
    exposed_names: frozenset[str]
    description: str
    markers: frozenset[str]

@dataclass(frozen=True)
class DependencyGraph:
    repos: tuple[RepoNode, ...]
    edges: tuple[Edge, ...]
    roles: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]
    cache_summary: dict[str, object] | None = field(default=None, compare=False)

@dataclass(frozen=True)
class GraphProgress:
    """Observed work, never an estimate of source coverage or semantic truth."""

    phase: str
    completed_repos: int
    total_repos: int
    elapsed_ms: int

@dataclass(frozen=True)
class _RepoBuild:
    name: str
    node: RepoNode
    exposed_names: set[str]
    raw_edges: list[RawEdge]
    markers: set[str]
    cache_outcome: str = "bypassed"
    cache_reason: str = "not_recorded"
    cache_written: bool = False
    cache_stats: dict[str, int] = field(default_factory=dict, compare=False)

def detect_markers(repo_root: Path, exposed: set[str]) -> set[str]:
    mk: set[str] = set()
    if exposed:
        mk.add("published")
    pp = repo_root / "pyproject.toml"
    if pp.is_file():
        try:
            data = tomllib.loads(read_source_text(pp, encoding="utf-8", errors="replace"))
            if data.get("project", {}).get("scripts") or \
               data.get("project", {}).get("entry-points"):
                mk.add("entry")
        except (tomllib.TOMLDecodeError, OSError):
            pass
    cfg = repo_root / "setup.cfg"
    if cfg.is_file():
        try:
            cp = configparser.ConfigParser()
            cp.read_string(read_source_text(cfg, encoding="utf-8", errors="strict"))
            if cp.has_option("options.entry_points", "console_scripts"):
                mk.add("entry")
        except (configparser.Error, OSError):
            pass
    pj = repo_root / "package.json"
    if pj.is_file():
        try:
            if json.loads(read_source_text(pj, encoding="utf-8", errors="replace")).get("bin"):
                mk.add("entry")
        except (json.JSONDecodeError, OSError):
            pass
    if any(walk_files(repo_root, names=("__main__.py",), stop_at_nested_repos=True)):
        mk.add("entry")
    return mk

def _default_jobs() -> int:
    return min(32, (os.cpu_count() or 4) * 5)

def _build_one_repo(item: tuple[str, Path], resolvers) -> _RepoBuild:
    name, root = item
    ecos: list[str] = []
    names: set[str] = set()
    raws: list[RawEdge] = []
    for resolver in resolvers:
        if resolver.matches(root):
            ecos.append(resolver.name)
            names |= resolver.exposed_names(root)
            raws += resolver.raw_edges(root)
    mk = detect_markers(root, names)
    node = RepoNode(name, str(root), tuple(ecos), frozenset(names), _description(root), frozenset(mk))
    return _RepoBuild(name, node, names, raws, mk)

def _repo_build_to_json(build: _RepoBuild) -> dict:
    return {
        "node": {
            "name": build.node.name,
            "path": build.node.path,
            "ecosystems": list(build.node.ecosystems),
            "exposed_names": sorted(build.node.exposed_names),
            "description": build.node.description,
            "markers": sorted(build.node.markers),
        },
        "exposed_names": sorted(build.exposed_names),
        "raw_edges": [
            {
                "target_name": edge.target_name,
                "signal": edge.signal,
                "evidence_file": edge.evidence_file,
                "evidence_line": edge.evidence_line,
                "raw_spec": edge.raw_spec,
            }
            for edge in build.raw_edges
        ],
        "markers": sorted(build.markers),
    }

def _repo_build_from_json(data: dict) -> _RepoBuild:
    node = data["node"]
    return _RepoBuild(
        name=str(node["name"]),
        node=RepoNode(
            name=str(node["name"]),
            path=str(node["path"]),
            ecosystems=tuple(str(item) for item in node.get("ecosystems", ())),
            exposed_names=frozenset(str(item) for item in node.get("exposed_names", ())),
            description=str(node.get("description", "")),
            markers=frozenset(str(item) for item in node.get("markers", ())),
        ),
        exposed_names=set(str(item) for item in data.get("exposed_names", ())),
        raw_edges=[
            RawEdge(
                str(edge["target_name"]),
                str(edge["signal"]),
                str(edge["evidence_file"]),
                edge.get("evidence_line"),
                str(edge["raw_spec"]),
            )
            for edge in data.get("raw_edges", ())
        ],
        markers=set(str(item) for item in data.get("markers", ())),
    )

def _load_or_build_one_repo(
    item: tuple[str, Path],
    resolvers,
    *,
    use_cache: bool,
) -> _RepoBuild:
    name, requested_root = item
    source_item = (name, requested_root.resolve())
    cache_stats = _cache.empty_repo_cache_stats()

    def presented(built: _RepoBuild) -> _RepoBuild:
        return replace(built, node=replace(built.node, path=str(requested_root)))

    cache_allowed = use_cache and _cache.resolvers_use_shared_source_reads(resolvers)
    with cached_file_scope():
        if not cache_allowed:
            build_started = perf_counter()
            built = _build_one_repo(source_item, resolvers)
            _cache.add_cache_timing(cache_stats, "fresh_build", build_started)
            return presented(replace(
                built,
                cache_outcome="bypassed",
                cache_reason="disabled_or_unsupported",
                cache_stats=cache_stats,
            ))
        lookup = make_lookup(name, source_item[1], resolvers, stats=cache_stats)
        cached, cache_outcome, cache_reason = _cache.read_repo_build_with_outcome(lookup, stats=cache_stats)
        if cached is not None:
            rehydrate_started = perf_counter()
            try:
                built = _repo_build_from_json(cached)
                _cache.add_cache_timing(cache_stats, "cache_rehydrate", rehydrate_started)
                return presented(replace(
                    built,
                    cache_outcome="hit",
                    cache_reason=cache_reason,
                    cache_stats=cache_stats,
                ))
            except (KeyError, TypeError, ValueError):
                _cache.add_cache_timing(cache_stats, "cache_rehydrate", rehydrate_started)
                cache_outcome = "invalid"
                cache_reason = "build_payload"
        build_started = perf_counter()
        built = _build_one_repo(source_item, resolvers)
        _cache.add_cache_timing(cache_stats, "fresh_build", build_started)
        cache_written = False
        if source_reuse_complete():
            cache_written = _cache.write_repo_build(lookup, _repo_build_to_json(built), stats=cache_stats)
        return presented(replace(
            built,
            cache_outcome=cache_outcome,
            cache_reason=cache_reason,
            cache_written=cache_written,
            cache_stats=cache_stats,
        ))

def _collect_repos(
    items: list[tuple[str, Path]],
    resolvers,
    jobs: int,
    *,
    use_cache: bool,
    executor: str = "thread",
) -> Iterator[_RepoBuild]:
    if jobs <= 1 or len(items) <= 1:
        for item in items:
            yield _load_or_build_one_repo(item, resolvers, use_cache=use_cache)
        return
    # Spawn avoids inheriting locks or application state from an MCP host. The
    # Python API retains threads by default for local/custom resolver objects.
    pool_context = (
        ProcessPoolExecutor(max_workers=jobs, mp_context=multiprocessing.get_context("spawn"))
        if executor == "process" else ThreadPoolExecutor(max_workers=jobs)
    )
    with pool_context as pool:
        pending = [pool.submit(_load_or_build_one_repo, item, resolvers,
                               use_cache=use_cache) for item in items]
        try:
            for future in as_completed(pending):
                yield future.result()
        except BaseException:
            # A failed scan or cancelled consumer cannot use any later result.
            # Stop queued work before the context waits for active workers.
            for future in pending:
                future.cancel()
            raise

def build_graph(
    repo_paths: dict[str, Path],
    resolvers=ALL_RESOLVERS,
    *,
    jobs: int | None = None,
    use_cache: bool = True,
    on_progress: Callable[[GraphProgress], None] | None = None,
    executor: str = "thread",
) -> DependencyGraph:
    """Build complete dependency evidence; optional progress runs in the caller.

    Process workers are opt-in for Python callers, require picklable resolvers
    and a guarded main entrypoint, and default to at most four workers. CLI/MCP
    entrypoints select them to avoid Python parser contention across repos.
    """
    if executor not in {"thread", "process"}:
        raise ValueError("executor must be 'thread' or 'process'")
    nodes: list[RepoNode] = []
    exposed: dict[str, set[str]] = {}
    repo_raw: dict[str, list[RawEdge]] = {}
    markers: dict[str, set[str]] = {}
    cache_summary = _cache.empty_cache_summary()
    default_jobs = min(4, os.cpu_count() or 1) if executor == "process" else _default_jobs()
    worker_count = default_jobs if jobs is None else max(1, jobs)
    started = perf_counter()

    def report(phase: str) -> None:
        if on_progress is not None:
            on_progress(GraphProgress(phase, len(nodes), len(repo_paths),
                                      int((perf_counter() - started) * 1000)))

    try:
        report("building")
        for built in _collect_repos(
            sorted(repo_paths.items()), resolvers, worker_count, use_cache=use_cache,
            executor=executor,
        ):
            _cache.record_cache_summary(
                cache_summary,
                built.cache_outcome,
                built.cache_reason,
                built.cache_written,
                built.cache_stats,
            )
            exposed[built.name] = built.exposed_names
            repo_raw[built.name] = built.raw_edges
            markers[built.name] = built.markers
            nodes.append(built.node)
            report("building")

        # Completion order is for observability only. Preserve stable graph order.
        nodes.sort(key=lambda node: node.name)
        exposed = dict(sorted(exposed.items()))
        repo_raw = dict(sorted(repo_raw.items()))
        markers = dict(sorted(markers.items()))
        report("resolving")
        index = build_index(exposed)
        edges, warnings = resolve_edges(repo_raw, index)
        roles = derive_roles(set(repo_paths), edges, markers)
        graph = DependencyGraph(
            tuple(nodes),
            tuple(edges),
            roles,
            tuple(warnings),
            _cache.final_cache_summary(cache_summary),
        )
    except BaseException:
        report("failed")
        raise
    report("complete")
    return graph
