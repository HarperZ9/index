"""Per-repo graph resolver cache.

The cache stores derived resolver facts, never raw source. A repo entry is valid
only for the same repo key, resolved path, resolver signature, and graph-relevant
content fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..freshness.fingerprint import repo_fingerprint

SCHEMA = "index.graph-repo-cache/v1"
CACHE_KEY_VERSION = "repo-build/v1"
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


def _resolver_signature(resolvers) -> tuple[str, ...]:
    parts = []
    for resolver in resolvers:
        cls = type(resolver)
        name = str(getattr(resolver, "name", cls.__name__))
        parts.append(f"{name}:{cls.__module__}.{cls.__qualname__}")
    return tuple(sorted(parts))


def _file_digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "unreadable"


def repo_graph_fingerprint(repo_root: Path, resolvers) -> str:
    """Fingerprint resolver-relevant content plus description files.

    `repo_fingerprint` covers files read by resolvers. The graph node also carries
    README/package descriptions, so the repo graph cache includes those root docs
    to avoid stale inventory text.
    """
    root = Path(repo_root)
    parts = [repo_fingerprint(root, resolvers)]
    for name in _DESCRIPTION_NAMES:
        path = root / name
        if path.is_file():
            parts.append(f"{name}:{_file_digest(path)}")
        else:
            parts.append(f"{name}:missing")
    return _sha256_text("|".join(parts))


def make_lookup(repo_name: str, repo_root: Path, resolvers) -> RepoCacheLookup:
    root = Path(repo_root).resolve()
    fingerprint = repo_graph_fingerprint(root, resolvers)
    signature = _resolver_signature(resolvers)
    payload = {
        "version": CACHE_KEY_VERSION,
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


def read_repo_build(lookup: RepoCacheLookup) -> dict[str, Any] | None:
    try:
        data = json.loads(lookup.path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if data.get("schema") != SCHEMA:
        return None
    if data.get("repo_name") != lookup.repo_name:
        return None
    if data.get("repo_path") != lookup.repo_path:
        return None
    if data.get("fingerprint") != lookup.fingerprint:
        return None
    if tuple(data.get("resolver_signature") or ()) != lookup.resolver_signature:
        return None
    build = data.get("build")
    return build if isinstance(build, dict) else None


def write_repo_build(lookup: RepoCacheLookup, build: dict[str, Any]) -> None:
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
    except OSError:
        pass
