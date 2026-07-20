"""Scoped manifests with bounded metadata and strict content validation."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import os
from pathlib import Path, PurePosixPath
from time import time

from ..config import load_config
from ..freshness.fingerprint import is_relevant_filename
from ..graph.walk import EXCLUDE_DIRS
from ..scan import discover_repos

MANIFEST_SCHEMA = "index.route-manifest/v1"


def _stat(path: Path, root: Path) -> dict:
    value = path.stat()
    return {
        "path": path.relative_to(root).as_posix(),
        "mtime_ns": value.st_mtime_ns,
        "size": value.st_size,
    }


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _root_id(root: Path) -> str:
    return _sha256_text(str(root.resolve()))[:16]


def _config_identity(root: Path) -> str:
    for name in (".index.toml", ".repomap.toml"):
        path = root / name
        try:
            if path.is_file():
                return _sha256_bytes(
                    name.encode("utf-8") + b"\0" + path.read_bytes()
                )
        except OSError:
            return _sha256_text(f"{name}\0unreadable")
    return _sha256_text("no-active-index-config")


def _fold_pairs(entries: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for path, content_digest in sorted(entries):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_digest.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _fold_paths(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _strict_fold(
    graph_signatures: Mapping[str, str | None],
    markdown_paths_signature: str | None,
    document_digests: Mapping[str, str],
) -> str | None:
    if (
        markdown_paths_signature is None
        or any(value is None for value in graph_signatures.values())
    ):
        return None
    digest = hashlib.sha256()
    for repo_id, signature in sorted(graph_signatures.items()):
        digest.update(b"repo\0")
        digest.update(repo_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(signature).encode("ascii"))
        digest.update(b"\n")
    digest.update(b"markdown\0")
    digest.update(markdown_paths_signature.encode("ascii"))
    digest.update(b"\n")
    for path, content_digest in sorted(document_digests.items()):
        digest.update(b"document\0")
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_digest.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _map_path(root: Path, snapshot: Mapping) -> Path:
    evidence = snapshot.get("map")
    if isinstance(evidence, Mapping) and isinstance(evidence.get("path"), str):
        relative = PurePosixPath(evidence["path"])
        if not relative.is_absolute() and ".." not in relative.parts:
            return root.joinpath(*relative.parts)
    return root / "WORKSPACE-REPO-MAP.json"


def _map_evidence(root: Path, snapshot: Mapping) -> dict:
    path = _map_path(root, snapshot)
    try:
        relative = path.relative_to(root).as_posix()
        digest = _sha256_bytes(path.read_bytes())
    except (OSError, ValueError):
        relative = "WORKSPACE-REPO-MAP.json"
        digest = "missing"
    return {"path": relative, "sha256": digest}


def _scan_repositories(root: Path, repositories, budget, *, strict: bool) -> dict:
    directories: list[dict] = []
    files: list[dict] = []
    graph_signatures: dict[str, str | None] = {}
    markdown_paths: list[str] = []
    markdown_set: set[str] = set()
    missing_repositories: list[str] = []
    complete = True

    for candidate in repositories:
        repo_id = candidate.id
        repo = candidate.path
        graph_entries: list[tuple[str, str]] = []
        if repo is None or not repo.is_dir() or not (repo / ".git").exists():
            graph_signatures[repo_id] = None
            missing_repositories.append(repo_id)
            continue
        try:
            repo.relative_to(root)
        except ValueError:
            graph_signatures[repo_id] = None
            complete = False
            continue

        for dirpath, dirnames, filenames in os.walk(
            repo, onerror=lambda _error: None
        ):
            if not budget.checkpoint(
                "manifest.directory", counter="directories_visited"
            ):
                complete = False
                dirnames.clear()
                break
            directory = Path(dirpath)
            try:
                directories.append(_stat(directory, root))
            except (OSError, ValueError):
                complete = False
                dirnames.clear()
                break
            dirnames[:] = sorted(
                name for name in dirnames if name not in EXCLUDE_DIRS
            )
            for filename in sorted(filenames):
                relevant = is_relevant_filename(filename)
                markdown = filename.lower().endswith(".md")
                if not relevant and not markdown:
                    continue
                counter = (
                    "candidate_documents_observed" if markdown
                    else "files_validated"
                )
                if not budget.checkpoint("manifest.file", counter=counter):
                    complete = False
                    dirnames.clear()
                    break
                path = directory / filename
                try:
                    record = _stat(path, root)
                except (OSError, ValueError):
                    complete = False
                    continue
                record["graph"] = relevant
                record["markdown"] = markdown
                if relevant and strict:
                    try:
                        content_digest = _sha256_bytes(path.read_bytes())
                    except OSError:
                        content_digest = "unreadable"
                    record["digest"] = content_digest
                    graph_entries.append(
                        (path.relative_to(repo).as_posix(), content_digest)
                    )
                files.append(record)
                if markdown:
                    relative = record["path"]
                    if relative not in markdown_set:
                        markdown_set.add(relative)
                        markdown_paths.append(relative)
            if budget.exhausted:
                break
        graph_signatures[repo_id] = (
            _fold_pairs(graph_entries) if strict and not budget.exhausted else None
        )
        if budget.exhausted:
            complete = False
            break

    for candidate in repositories[len(graph_signatures):]:
        graph_signatures[candidate.id] = None
    directories.sort(key=lambda item: item["path"])
    files.sort(key=lambda item: item["path"])
    return {
        "complete": complete and not budget.exhausted,
        "directories": directories,
        "files": files,
        "graph_signatures": graph_signatures,
        "markdown_paths": sorted(markdown_paths),
        "missing_repositories": missing_repositories,
    }


def build_manifest(
    root,
    repositories,
    budget,
    *,
    scope_snapshot: dict,
    strict: bool,
    document_bodies: Mapping[str, str] | None = None,
) -> dict:
    """Build evidence scoped to the already selected repository roots."""
    root = Path(root).resolve()
    repositories = list(repositories)
    scan = _scan_repositories(root, repositories, budget, strict=strict)
    snapshot = deepcopy(scope_snapshot)
    if snapshot.get("kind") in {"workspace-map", "map"}:
        snapshot["map"] = _map_evidence(root, snapshot)

    markdown_paths = set(scan["markdown_paths"])
    document_digests: dict[str, str] = {}
    if strict and document_bodies:
        for path, body in sorted(document_bodies.items()):
            normalized = PurePosixPath(path)
            if (
                isinstance(path, str)
                and isinstance(body, str)
                and not normalized.is_absolute()
                and ".." not in normalized.parts
                and normalized.as_posix() in markdown_paths
            ):
                document_digests[normalized.as_posix()] = _sha256_text(body)

    markdown_signature = (
        _fold_paths(scan["markdown_paths"])
        if strict and scan["complete"] and not scan["missing_repositories"]
        else None
    )
    strict_signature = (
        _strict_fold(
            scan["graph_signatures"], markdown_signature, document_digests
        )
        if strict and scan["complete"] and not scan["missing_repositories"]
        else None
    )
    return {
        "schema": MANIFEST_SCHEMA,
        "complete": scan["complete"] and not scan["missing_repositories"],
        "root_id": _root_id(root),
        "config_id": _config_identity(root),
        "scope_snapshot": snapshot,
        "repositories": [candidate.id for candidate in repositories],
        "directories": scan["directories"],
        "files": scan["files"],
        "graph_signatures": scan["graph_signatures"],
        "markdown_paths_signature": markdown_signature,
        "document_digests": document_digests,
        "strict_signature": strict_signature,
        "last_strict_verified_at": time()
        if strict and scan["complete"] and not scan["missing_repositories"]
        else None,
    }


def _counts(manifest: Mapping) -> tuple[dict, dict]:
    unchecked = {
        "directories": len(manifest.get("directories", ())),
        "files": len(manifest.get("files", ())),
        "documents": len(manifest.get("document_digests", ())),
    }
    return {name: 0 for name in unchecked}, unchecked


def _result(
    status: str,
    checked: dict,
    unchecked: dict,
    *,
    exhausted_at: str | None = None,
) -> dict:
    return {
        "status": status,
        "checked": checked,
        "unchecked": unchecked,
        "exhausted_at": exhausted_at,
    }


def _unknown(manifest: Mapping, budget) -> dict:
    checked, unchecked = _counts(manifest)
    return _result(
        "UNKNOWN",
        checked,
        unchecked,
        exhausted_at=budget.exhausted_at,
    )


def _candidate_universe(
    root: Path, manifest: Mapping, budget, *, strict: bool
) -> str:
    snapshot = manifest.get("scope_snapshot")
    if not isinstance(snapshot, Mapping):
        return "DRIFT"
    kind = snapshot.get("kind")
    if kind == "explicit":
        return "FRESH"
    if not snapshot.get("complete", False):
        if kind not in {"workspace-map", "map"}:
            return "UNKNOWN"
        map_evidence = snapshot.get("map")
        if not isinstance(map_evidence, Mapping):
            return "DRIFT"
        if _map_evidence(root, snapshot) != dict(map_evidence):
            return "DRIFT"
        return "UNKNOWN" if strict else "FRESH"
    if kind in {"workspace-map", "map"}:
        map_evidence = snapshot.get("map")
        if (
            not isinstance(map_evidence, Mapping)
            or _map_evidence(root, snapshot) != dict(map_evidence)
        ):
            return "DRIFT"
    if kind not in {"discovery", "workspace-map", "map"}:
        return "DRIFT"

    config = load_config(None, root)
    skipped: list = []
    discovered = discover_repos(
        root,
        config,
        skipped=skipped,
        checkpoint=budget.callback("directories_visited"),
        prune_repo_contents=True,
    )
    if budget.exhausted or skipped:
        return "UNKNOWN"
    discovered_ids = sorted(
        path.relative_to(root).as_posix() or "." for path in discovered
    )
    cached_ids = sorted(snapshot.get("candidate_ids", ()))
    return "FRESH" if discovered_ids == cached_ids else "DRIFT"


def _validate_stats(root: Path, manifest: Mapping, budget) -> dict:
    checked, unchecked = _counts(manifest)
    for kind, boundary in (
        ("directories", "manifest.directory"),
        ("files", "manifest.file"),
    ):
        records = manifest.get(kind, ())
        for record in records:
            counter = (
                "directories_visited"
                if kind == "directories"
                else "files_validated"
            )
            if not budget.checkpoint(boundary, counter=counter):
                return _result(
                    "UNKNOWN",
                    checked,
                    unchecked,
                    exhausted_at=budget.exhausted_at,
                )
            try:
                current = _stat(root.joinpath(*record["path"].split("/")), root)
            except (OSError, KeyError, TypeError, ValueError):
                return _result("DRIFT", checked, unchecked)
            checked[kind] += 1
            unchecked[kind] -= 1
            if any(
                current[field] != record.get(field)
                for field in ("path", "mtime_ns", "size")
            ):
                return _result("DRIFT", checked, unchecked)
    return _result("FRESH", checked, unchecked)


def _strict_repositories(root: Path, manifest: Mapping):
    from .scope import RepoCandidate

    result = []
    for repo_id in manifest.get("repositories", ()):
        path = root if repo_id == "." else root.joinpath(*repo_id.split("/"))
        result.append(RepoCandidate(repo_id, path, repo_id, "manifest"))
    return result


def _validate_strict(root: Path, manifest: Mapping, budget) -> dict:
    checked, unchecked = _counts(manifest)
    repositories = _strict_repositories(root, manifest)
    scan = _scan_repositories(root, repositories, budget, strict=True)
    cached_directory_paths = {
        record.get("path") for record in manifest.get("directories", ())
    }
    cached_file_paths = {
        record.get("path") for record in manifest.get("files", ())
    }
    checked["directories"] = sum(
        record.get("path") in cached_directory_paths
        for record in scan["directories"]
    )
    checked["files"] = sum(
        record.get("path") in cached_file_paths for record in scan["files"]
    )
    unchecked["directories"] -= checked["directories"]
    unchecked["files"] -= checked["files"]
    if scan["missing_repositories"]:
        return _result("DRIFT", checked, unchecked)
    if not scan["complete"]:
        return _result(
            "UNKNOWN",
            checked,
            unchecked,
            exhausted_at=budget.exhausted_at,
        )
    markdown_signature = _fold_paths(scan["markdown_paths"])
    if (
        scan["graph_signatures"] != manifest.get("graph_signatures")
        or markdown_signature != manifest.get("markdown_paths_signature")
    ):
        return _result("DRIFT", checked, unchecked)

    document_digests: dict[str, str] = {}
    markdown_paths = set(scan["markdown_paths"])
    selected_roots = [
        candidate.path.resolve() for candidate in repositories
        if candidate.path is not None
    ]
    for path, expected in sorted(manifest.get("document_digests", {}).items()):
        target = root.joinpath(*path.split("/"))
        try:
            resolved_target = target.resolve(strict=True)
            selected = any(
                resolved_target.is_relative_to(repository)
                for repository in selected_roots
            )
        except (OSError, RuntimeError):
            selected = False
        if path not in markdown_paths or not selected:
            return _result("DRIFT", checked, unchecked)
        if not budget.checkpoint(
            "docs.open", counter="document_bodies_opened"
        ):
            return _result(
                "UNKNOWN",
                checked,
                unchecked,
                exhausted_at=budget.exhausted_at,
            )
        try:
            body = target.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):
            return _result("DRIFT", checked, unchecked)
        actual = _sha256_text(body)
        document_digests[path] = actual
        checked["documents"] += 1
        unchecked["documents"] -= 1
        if actual != expected:
            return _result("DRIFT", checked, unchecked)
    signature = _strict_fold(
        scan["graph_signatures"], markdown_signature, document_digests
    )
    return _result(
        "FRESH" if signature == manifest.get("strict_signature") else "DRIFT",
        checked,
        unchecked,
    )


def validate_manifest(root, manifest, budget, *, strict: bool) -> dict:
    """Validate cached evidence, returning FRESH, DRIFT, or UNKNOWN."""
    root = Path(root).resolve()
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("root_id") != _root_id(root)
        or manifest.get("config_id") != _config_identity(root)
    ):
        checked, unchecked = _counts(manifest if isinstance(manifest, Mapping) else {})
        return _result("DRIFT", checked, unchecked)
    if not manifest.get("complete", False):
        return _unknown(manifest, budget)
    universe = _candidate_universe(root, manifest, budget, strict=strict)
    if universe == "DRIFT":
        checked, unchecked = _counts(manifest)
        return _result("DRIFT", checked, unchecked)
    if universe == "UNKNOWN":
        return _unknown(manifest, budget)
    if strict:
        return _validate_strict(root, manifest, budget)
    return _validate_stats(root, manifest, budget)
