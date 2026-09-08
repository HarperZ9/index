"""Assemble repo trees + resolvers into a DependencyGraph."""
from __future__ import annotations

import configparser
import json
import os
import re
import tomllib
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

from .edges import Edge, build_index, resolve_edges
from .cache import (
    make_lookup,
    read_repo_build,
    resolvers_use_shared_source_reads,
    write_repo_build,
)
from .walk import cached_file_scope, read_source_text, source_reuse_complete, walk_files
from .resolvers import ALL_RESOLVERS
from .resolvers.base import RawEdge
from .roles import derive_roles

_PARA = re.compile(r"\n\s*\n")


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


def _description(repo_root: Path) -> str:
    for readme in ("README.md", "README.rst", "README.txt", "readme.md"):
        p = repo_root / readme
        if p.is_file():
            try:
                text = read_source_text(p, encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            for block in _PARA.split(text):
                b = block.strip()
                if b and not b.startswith("#") and not b.startswith("!["):
                    return " ".join(b.split())[:300]
    pp = repo_root / "pyproject.toml"
    if pp.is_file():
        try:
            d = tomllib.loads(read_source_text(pp, encoding="utf-8", errors="replace")).get("project", {})
            if d.get("description"):
                return str(d["description"])
        except (tomllib.TOMLDecodeError, OSError):
            pass
    pj = repo_root / "package.json"
    if pj.is_file():
        try:
            d = json.loads(read_source_text(pj, encoding="utf-8", errors="replace"))
            if d.get("description"):
                return str(d["description"])
        except (json.JSONDecodeError, OSError):
            pass
    return "(no description)"


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
    node = RepoNode(
        name,
        str(root),
        tuple(ecos),
        frozenset(names),
        _description(root),
        frozenset(mk),
    )
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

    def presented(built: _RepoBuild) -> _RepoBuild:
        return replace(built, node=replace(built.node, path=str(requested_root)))

    cache_allowed = use_cache and resolvers_use_shared_source_reads(resolvers)
    with cached_file_scope():
        if not cache_allowed:
            return presented(_build_one_repo(source_item, resolvers))
        lookup = make_lookup(name, source_item[1], resolvers)
        cached = read_repo_build(lookup)
        if cached is not None:
            try:
                return presented(_repo_build_from_json(cached))
            except (KeyError, TypeError, ValueError):
                pass
        built = _build_one_repo(source_item, resolvers)
        if source_reuse_complete():
            write_repo_build(lookup, _repo_build_to_json(built))
        return presented(built)


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
        graph = DependencyGraph(tuple(nodes), tuple(edges), roles, tuple(warnings))
    except BaseException:
        report("failed")
        raise
    report("complete")
    return graph
