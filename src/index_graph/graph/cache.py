"""Per-repo graph resolver cache.

The cache stores derived resolver facts, never raw source. A repo entry is valid
only for the same repo key, resolved path, resolver signature, graph-relevant
content fingerprint, and resolver source-read contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import CodeType
from typing import Any

from .walk import read_source_bytes
from .resolvers import BUILTIN_SHARED_SOURCE_READER_TYPES
from .cache_metrics import (
    add_cache_stat,
    add_cache_timing,
    empty_cache_summary,
    empty_repo_cache_stats,
    final_cache_summary,
    record_cache_summary,
)
from .. import __version__
from ..freshness.fingerprint import repo_fingerprint

SCHEMA = "index.graph-repo-cache/v1"
CACHE_KEY_VERSION = "repo-build/v4"
_DESCRIPTION_NAMES = ("README.md", "README.rst", "README.txt", "readme.md")


@dataclass(frozen=True)
class RepoCacheLookup:
    key: str
    path: Path
    repo_name: str
    repo_path: str
    fingerprint: str
    resolver_signature: tuple[str, ...]


def _cache_dir() -> Path:
    raw = os.environ.get("INDEX_GRAPH_REPO_CACHE_DIR")
    if raw:
        return Path(raw)
    raw = os.environ.get("INDEX_CACHE_DIR")
    if raw:
        return Path(raw) / "graph-repos"
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "index_graph" / "cache" / "graph-repos"
    return Path.home() / ".cache" / "index_graph" / "graph-repos"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _implementation_value(value):
    """Encode immutable code values without marshal's object-reference state."""
    if isinstance(value, CodeType):
        fields = ("co_argcount", "co_posonlyargcount", "co_kwonlyargcount",
                  "co_nlocals", "co_stacksize", "co_flags", "co_code",
                  "co_consts", "co_names", "co_varnames", "co_freevars",
                  "co_cellvars", "co_exceptiontable")
        return ["code", [[name, _implementation_value(getattr(value, name, None))]
                         for name in fields]]
    if isinstance(value, tuple):
        return ["tuple", [_implementation_value(item) for item in value]]
    if isinstance(value, frozenset):
        items = [_implementation_value(item) for item in value]
        return ["frozenset", sorted(items, key=lambda item: json.dumps(item))]
    if isinstance(value, bytes):
        return ["bytes", value.hex()]
    return [type(value).__name__, repr(value)]


def _resolver_signature(resolvers) -> tuple[str, ...]:
    parts = []
    for resolver in resolvers:
        cls = type(resolver)
        name = str(getattr(resolver, "name", cls.__name__))
        implementation = hashlib.sha256()
        implementation.update(str(sys.implementation.cache_tag).encode("utf-8"))
        for method_name in sorted(dir(cls)):
            method = getattr(cls, method_name, None)
            code = getattr(method, "__code__", None)
            if code is not None:
                implementation.update(method_name.encode("utf-8"))
                implementation.update(json.dumps(_implementation_value(code),
                                                  separators=(",", ":")).encode("utf-8"))
        # Custom resolvers with external configuration can invalidate their
        # derived facts explicitly. Package version covers shipped helper changes.
        implementation.update(str(getattr(resolver, "cache_version", "1")).encode("utf-8"))
        parts.append(f"{name}:{cls.__module__}.{cls.__qualname__}:{implementation.hexdigest()}")
    return tuple(sorted(parts))


def resolver_uses_shared_source_reads(resolver) -> bool:
    """Whether a resolver can safely participate in persistent repo caching."""
    if type(resolver) in BUILTIN_SHARED_SOURCE_READER_TYPES:
        return True
    return getattr(resolver, "uses_shared_source_reader", False) is True


def resolvers_use_shared_source_reads(resolvers) -> bool:
    return all(resolver_uses_shared_source_reads(resolver) for resolver in resolvers)


def _file_digest(path: Path, stats: dict[str, int] | None = None) -> str:
    started = perf_counter()
    try:
        data = read_source_bytes(path)
        add_cache_stat(stats, "fingerprint_description_files", 1)
        add_cache_stat(stats, "fingerprint_description_bytes", len(data))
        return hashlib.sha256(data).hexdigest()
    except OSError:
        add_cache_stat(stats, "fingerprint_description_unreadable", 1)
        return "unreadable"
    finally:
        add_cache_timing(stats, "description_read_hash", started)


def repo_graph_fingerprint(repo_root: Path, resolvers, stats: dict[str, int] | None = None) -> str:
    """Fingerprint resolver-relevant content plus description files.

    `repo_fingerprint` covers files read by resolvers. The graph node also carries
    README/package descriptions, so the repo graph cache includes those root docs
    to avoid stale inventory text.
    """
    root = Path(repo_root)
    parts = [repo_fingerprint(root, resolvers, stats=stats)]
    for name in _DESCRIPTION_NAMES:
        path = root / name
        if path.is_file():
            parts.append(f"{name}:{_file_digest(path, stats=stats)}")
        else:
            parts.append(f"{name}:missing")
    return _sha256_text("|".join(parts))


def make_lookup(repo_name: str, repo_root: Path, resolvers, stats: dict[str, int] | None = None) -> RepoCacheLookup:
    root = Path(repo_root).resolve()
    started = perf_counter()
    fingerprint = repo_graph_fingerprint(root, resolvers, stats=stats)
    add_cache_timing(stats, "fingerprint", started)
    started = perf_counter()
    signature = _resolver_signature(resolvers)
    add_cache_timing(stats, "resolver_signature", started)
    payload = {
        "version": CACHE_KEY_VERSION,
        "index_version": __version__,
        "repo_name": repo_name,
        "repo_path": str(root),
        "fingerprint": fingerprint,
        "resolver_signature": signature,
    }
    key = _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return RepoCacheLookup(
        key=key,
        path=_cache_dir() / f"{key}.json",
        repo_name=repo_name,
        repo_path=str(root),
        fingerprint=fingerprint,
        resolver_signature=signature,
    )


def read_repo_build_with_outcome(
    lookup: RepoCacheLookup, stats: dict[str, int] | None = None
) -> tuple[dict[str, Any] | None, str, str]:
    started = perf_counter()
    try:
        raw = lookup.path.read_text(encoding="utf-8")
    except FileNotFoundError:
        add_cache_timing(stats, "cache_read", started)
        return None, "miss", "not_found"
    except OSError:
        add_cache_timing(stats, "cache_read", started)
        return None, "invalid", "unreadable"
    add_cache_timing(stats, "cache_read", started)
    started = perf_counter()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        add_cache_timing(stats, "cache_decode", started)
        return None, "invalid", "invalid_json"
    add_cache_timing(stats, "cache_decode", started)
    if data.get("schema") != SCHEMA:
        return None, "invalid", "schema"
    if data.get("repo_name") != lookup.repo_name:
        return None, "invalid", "repo_name"
    if data.get("repo_path") != lookup.repo_path:
        return None, "invalid", "repo_path"
    if data.get("fingerprint") != lookup.fingerprint:
        return None, "invalid", "fingerprint"
    if tuple(data.get("resolver_signature") or ()) != lookup.resolver_signature:
        return None, "invalid", "resolver_signature"
    build = data.get("build")
    if not isinstance(build, dict):
        return None, "invalid", "build"
    return build, "hit", "hit"


def read_repo_build(lookup: RepoCacheLookup) -> dict[str, Any] | None:
    build, _outcome, _reason = read_repo_build_with_outcome(lookup)
    return build


def write_repo_build(
    lookup: RepoCacheLookup, build: dict[str, Any], stats: dict[str, int] | None = None
) -> bool:
    started = perf_counter()
    payload = {
        "schema": SCHEMA,
        "version": CACHE_KEY_VERSION,
        "repo_name": lookup.repo_name,
        "repo_path": lookup.repo_path,
        "fingerprint": lookup.fingerprint,
        "resolver_signature": list(lookup.resolver_signature),
        "build": build,
    }
    try:
        lookup.path.parent.mkdir(parents=True, exist_ok=True)
        lookup.path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False
    finally:
        add_cache_timing(stats, "cache_write", started)
