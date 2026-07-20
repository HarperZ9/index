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
from .freshness import (
    MANIFEST_SCHEMA,
    is_normalized_relative_path,
    validate_manifest_paths,
)
from .model import REASON_CODES, ROUTE_SCHEMA

CACHE_SCHEMA = "index.route-cache-entry/v1"
_MEMORY: dict[tuple[str, str], dict] = {}
_RECEIPT_FIELDS = {
    "schema", "verdict", "root", "query", "freshness", "budget", "scope",
    "selection", "documents", "evidence", "reconciliation", "recheck",
}
_VERDICTS = {"MATCH", "PARTIAL", "STALE", "UNVERIFIABLE"}
_MANIFEST_FIELDS = {
    "schema", "complete", "root_id", "config_id", "scope_snapshot",
    "repositories", "directories", "files", "graph_signatures",
    "markdown_paths_signature", "document_digests", "strict_signature",
    "last_strict_verified_at",
}


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
        and _valid_payload(payload)
        and _valid_manifest(manifest)
        and _compatible_payload_manifest(payload, manifest)
        and isinstance(entry.get("markdown"), str)
    )


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_route_item(value: object, *, allow_root: bool = False) -> bool:
    return (
        isinstance(value, dict)
        and is_normalized_relative_path(
            value.get("path"), allow_root=allow_root
        )
        and isinstance(value.get("reason_code"), str)
        and value["reason_code"] in REASON_CODES
        and isinstance(value.get("rule_ref"), str)
        and bool(value["rule_ref"].strip())
        and isinstance(value.get("evidence"), dict)
    )


def _valid_route_items(values: object, *, allow_root: bool = False) -> bool:
    return (
        isinstance(values, list)
        and all(
            _valid_route_item(item, allow_root=allow_root)
            for item in values
        )
        and len([item["path"] for item in values])
        == len({item["path"] for item in values})
    )


def _valid_reconciliation(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    counts = value.get("counts")
    failures = value.get("failures")
    return (
        isinstance(value.get("verdict"), str)
        and value["verdict"] in {"MATCH", "DRIFT"}
        and isinstance(counts, dict)
        and set(counts) == {
            "candidates", "selected", "rejected", "omitted",
        }
        and all(_nonnegative_int(item) for item in counts.values())
        and isinstance(failures, list)
        and all(
            isinstance(item, dict)
            and set(item) == {"code", "detail"}
            and isinstance(item["code"], str)
            and bool(item["code"].strip())
            and isinstance(item["detail"], str)
            and bool(item["detail"].strip())
            for item in failures
        )
        and ((value["verdict"] == "MATCH") == (not failures))
    )


def _reconciliation_accounts(
    reconciliation: dict,
    candidates: list[str],
    selected: list[str],
    rejected: list[dict],
    omitted: list[dict],
) -> bool:
    booked = selected + [
        item["path"] for item in rejected + omitted
    ]
    return (
        reconciliation["counts"] == {
            "candidates": len(candidates),
            "selected": len(selected),
            "rejected": len(rejected),
            "omitted": len(omitted),
        }
        and len(booked) == len(set(booked))
        and sorted(candidates) == sorted(booked)
    )


def _valid_payload(payload: object) -> bool:
    if not isinstance(payload, dict) or set(payload) != _RECEIPT_FIELDS:
        return False
    freshness = payload.get("freshness")
    budget = payload.get("budget")
    scope = payload.get("scope")
    selection = payload.get("selection")
    documents = payload.get("documents")
    recheck = payload.get("recheck")
    if not (
        payload.get("schema") == ROUTE_SCHEMA
        and isinstance(payload.get("verdict"), str)
        and payload["verdict"] in _VERDICTS
        and payload.get("root") == "."
        and isinstance(payload.get("query"), str)
        and isinstance(freshness, dict)
        and isinstance(freshness.get("mode"), str)
        and freshness["mode"] in {"bounded", "strict"}
        and isinstance(freshness.get("validation"), str)
        and (
            freshness.get("cache_age_ms") is None
            or _nonnegative_int(freshness.get("cache_age_ms"))
        )
        and (
            freshness.get("source_signature") is None
            or isinstance(freshness.get("source_signature"), str)
        )
        and isinstance(freshness.get("recursive_complete"), bool)
        and isinstance(budget, dict)
        and set(budget) == {
            "requested_ms", "elapsed_ms", "repositories_visited",
            "directories_visited", "candidate_documents_observed",
            "document_bodies_opened", "files_validated", "exhausted_at",
        }
        and all(
            _nonnegative_int(budget[key])
            for key in set(budget) - {"exhausted_at"}
        )
        and (
            budget["exhausted_at"] is None
            or isinstance(budget["exhausted_at"], str)
        )
        and isinstance(scope, dict)
        and all(
            _nonnegative_int(scope.get(key))
            for key in ("max_repos", "max_docs", "budget_ms")
        )
        and isinstance(scope.get("paths"), list)
        and all(
            is_normalized_relative_path(path, allow_root=True)
            for path in scope["paths"]
        )
        and any(
            key.endswith("complete") and isinstance(value, bool)
            for key, value in scope.items()
        )
        and all(
            not key.endswith("complete") or isinstance(value, bool)
            for key, value in scope.items()
        )
        and isinstance(selection, dict)
        and set(selection) == {
            "candidates", "selected", "rejected", "omitted",
        }
        and all(
            isinstance(selection[key], list)
            for key in ("candidates", "selected", "rejected", "omitted")
        )
        and all(
            is_normalized_relative_path(path, allow_root=True)
            for key in ("candidates", "selected")
            for path in selection[key]
        )
        and all(
            len(selection[key]) == len(set(selection[key]))
            for key in ("candidates", "selected")
        )
        and all(
            _valid_route_items(selection[key], allow_root=True)
            for key in ("rejected", "omitted")
        )
        and isinstance(documents, dict)
        and set(documents) == {
            "selected", "rejected", "omitted", "reconciliation",
        }
        and isinstance(documents["selected"], list)
        and len(documents["selected"]) == len(set(documents["selected"]))
        and all(
            is_normalized_relative_path(path)
            for path in documents["selected"]
        )
        and all(
            _valid_route_items(documents[key])
            for key in ("rejected", "omitted")
        )
        and _valid_reconciliation(documents["reconciliation"])
        and isinstance(payload.get("evidence"), dict)
        and isinstance(payload["evidence"].get("router_pack"), dict)
        and _valid_reconciliation(payload.get("reconciliation"))
        and isinstance(recheck, dict)
        and set(recheck) == {"cli", "mcp"}
        and all(isinstance(value, str) and value for value in recheck.values())
    ):
        return False
    document_candidates = documents["selected"] + [
        item["path"]
        for item in documents["rejected"] + documents["omitted"]
    ]
    return (
        _reconciliation_accounts(
            payload["reconciliation"],
            selection["candidates"],
            selection["selected"],
            selection["rejected"],
            selection["omitted"],
        )
        and _reconciliation_accounts(
            documents["reconciliation"],
            document_candidates,
            documents["selected"],
            documents["rejected"],
            documents["omitted"],
        )
    )


def _compatible_payload_manifest(payload: dict, manifest: dict) -> bool:
    verdict = payload["verdict"]
    snapshot = manifest["scope_snapshot"]
    selection = payload["selection"]
    scope = payload["scope"]
    budget = payload["budget"]
    if not manifest["complete"] and verdict == "MATCH":
        return False
    if (
        snapshot["kind"] in {"workspace-map", "map"}
        and not snapshot["complete"]
        and verdict != "PARTIAL"
    ):
        return False
    if set(selection["selected"]) != set(manifest["repositories"]):
        return False
    if len(selection["selected"]) > scope["max_repos"]:
        return False
    if budget["document_bodies_opened"] > scope["max_docs"]:
        return False
    if len(manifest["document_digests"]) > scope["max_docs"]:
        return False
    if budget["requested_ms"] != scope["budget_ms"]:
        return False
    if payload["freshness"]["mode"] == "strict":
        signature = manifest.get("strict_signature")
        if payload["freshness"]["source_signature"] != signature:
            return False
        if (
            manifest["complete"] or verdict == "MATCH"
        ) and not isinstance(signature, str):
            return False
    if verdict == "MATCH":
        return (
            set(selection["candidates"]) == set(snapshot["candidate_ids"])
            and manifest["complete"]
            and snapshot["complete"]
            and payload["freshness"]["recursive_complete"]
            and budget["exhausted_at"] is None
            and all(
                value
                for key, value in scope.items()
                if key.endswith("complete")
            )
            and payload["reconciliation"]["verdict"] == "MATCH"
            and not payload["reconciliation"]["failures"]
            and payload["documents"]["reconciliation"]["verdict"] == "MATCH"
            and not payload["documents"]["reconciliation"]["failures"]
            and not selection["rejected"]
            and not selection["omitted"]
            and not payload["documents"]["rejected"]
            and not payload["documents"]["omitted"]
        )
    return True


def _valid_stat_record(record: object, *, file_record: bool) -> bool:
    if not isinstance(record, dict):
        return False
    valid = (
        is_normalized_relative_path(
            record.get("path"), allow_root=not file_record
        )
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
    if (
        not isinstance(manifest, dict)
        or not _MANIFEST_FIELDS.issubset(manifest)
    ):
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
    return validate_manifest_paths(manifest) and all(
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

    def _memory_key(self, key: str) -> tuple[str, str]:
        return str(self.directory.resolve()), key

    def get(self, key: str) -> dict | None:
        memory_key = self._memory_key(key)
        if memory_key in _MEMORY:
            entry = _MEMORY[memory_key]
            return deepcopy(entry) if _valid_entry(entry) else None
        try:
            entry = json.loads(self.path_for(key).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not _valid_entry(entry):
            return None
        _MEMORY[memory_key] = deepcopy(entry)
        return deepcopy(entry)

    def put(self, key: str, *, payload: dict, markdown: str, manifest: dict) -> None:
        entry = {
            "schema": CACHE_SCHEMA,
            "created_at": time(),
            "payload": deepcopy(payload),
            "markdown": markdown,
            "manifest": deepcopy(manifest),
        }
        _MEMORY[self._memory_key(key)] = deepcopy(entry)
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
