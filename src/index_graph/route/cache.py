"""Memory and disk cache for receipt-backed routes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from time import time

from .. import __version__
from .freshness import MANIFEST_SCHEMA
from .model import ROUTE_SCHEMA

CACHE_SCHEMA = "index.route-cache-entry/v1"
_MEMORY: dict[str, dict] = {}


def cache_identity(root: Path, request) -> str:
    """Return a route cache key without inspecting the workspace tree."""
    payload = {
        "tool_version": __version__,
        "route_schema": ROUTE_SCHEMA,
        "cache_schema": CACHE_SCHEMA,
        "root": str(Path(root).resolve()),
        "query": request.query,
        "paths": list(request.paths),
        "max_repos": request.max_repos,
        "max_docs": request.max_docs,
        "budget_ms": request.budget_ms,
        "freshness": request.freshness,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _valid_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    payload = entry.get("payload")
    manifest = entry.get("manifest")
    created_at = entry.get("created_at")
    return (
        entry.get("schema") == CACHE_SCHEMA
        and isinstance(created_at, (int, float))
        and not isinstance(created_at, bool)
        and isinstance(payload, dict)
        and payload.get("schema") == ROUTE_SCHEMA
        and _valid_manifest(manifest)
        and isinstance(entry.get("markdown"), str)
    )


def _valid_stat_record(record: object, *, file_record: bool) -> bool:
    if not isinstance(record, dict):
        return False
    valid = (
        isinstance(record.get("path"), str)
        and isinstance(record.get("mtime_ns"), int)
        and not isinstance(record.get("mtime_ns"), bool)
        and isinstance(record.get("size"), int)
        and not isinstance(record.get("size"), bool)
    )
    if not valid or not file_record:
        return valid
    return (
        isinstance(record.get("graph"), bool)
        and isinstance(record.get("markdown"), bool)
        and (
            "digest" not in record
            or isinstance(record.get("digest"), str)
        )
    )


def _valid_manifest(manifest: object) -> bool:
    if not isinstance(manifest, dict):
        return False
    snapshot = manifest.get("scope_snapshot")
    graph_signatures = manifest.get("graph_signatures")
    document_digests = manifest.get("document_digests")
    directories = manifest.get("directories")
    files = manifest.get("files")
    repositories = manifest.get("repositories")
    if not (
        manifest.get("schema") == MANIFEST_SCHEMA
        and isinstance(manifest.get("complete"), bool)
        and isinstance(manifest.get("root_id"), str)
        and isinstance(manifest.get("config_id"), str)
        and isinstance(snapshot, dict)
        and isinstance(snapshot.get("kind"), str)
        and isinstance(snapshot.get("complete"), bool)
        and isinstance(snapshot.get("candidate_ids"), list)
        and all(isinstance(value, str) for value in snapshot["candidate_ids"])
        and (
            snapshot.get("map") is None
            or isinstance(snapshot.get("map"), dict)
        )
        and isinstance(repositories, list)
        and all(isinstance(value, str) for value in repositories)
        and isinstance(directories, list)
        and all(
            _valid_stat_record(record, file_record=False)
            for record in directories
        )
        and isinstance(files, list)
        and all(_valid_stat_record(record, file_record=True) for record in files)
        and isinstance(graph_signatures, dict)
        and all(
            isinstance(key, str)
            and (isinstance(value, str) or value is None)
            for key, value in graph_signatures.items()
        )
        and isinstance(document_digests, dict)
        and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in document_digests.items()
        )
    ):
        return False
    return all(
        value is None or isinstance(value, expected)
        for value, expected in (
            (manifest.get("markdown_paths_signature"), str),
            (manifest.get("strict_signature"), str),
            (manifest.get("last_strict_verified_at"), (int, float)),
        )
    )


class RouteCache:
    def __init__(self, directory: Path | None = None):
        base = os.environ.get("INDEX_ROUTE_CACHE_DIR")
        local = os.environ.get("LOCALAPPDATA")
        self.directory = directory or (
            Path(base) if base else
            Path(local) / "index_graph" / "route-cache" if local else
            Path.home() / ".cache" / "index_graph" / "route-cache"
        )

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> dict | None:
        if key in _MEMORY:
            entry = _MEMORY[key]
            return deepcopy(entry) if _valid_entry(entry) else None
        try:
            entry = json.loads(self.path_for(key).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not _valid_entry(entry):
            return None
        _MEMORY[key] = deepcopy(entry)
        return deepcopy(entry)

    def put(self, key: str, *, payload: dict, markdown: str, manifest: dict) -> None:
        entry = {
            "schema": CACHE_SCHEMA,
            "created_at": time(),
            "payload": deepcopy(payload),
            "markdown": markdown,
            "manifest": deepcopy(manifest),
        }
        _MEMORY[key] = deepcopy(entry)
        temporary: Path | None = None
        try:
            path = self.path_for(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(entry, stream, separators=(",", ":"))
            os.replace(temporary, path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def clear_memory() -> None:
        _MEMORY.clear()
