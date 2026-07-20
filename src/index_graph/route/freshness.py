"""Scoped manifests with bounded metadata and strict content validation."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat as stat_module
from time import time

from ..config import load_config
from ..freshness.fingerprint import is_relevant_filename
from ..graph.walk import EXCLUDE_DIRS
from ..scan import discover_repos

MANIFEST_SCHEMA = "index.route-manifest/v1"


def is_normalized_relative_path(value: object, *, allow_root: bool = False) -> bool:
    """Whether *value* is a canonical root-relative POSIX path."""
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if value == ".":
        return allow_root
    return (
        not posix.is_absolute()
        and not windows.is_absolute()
        and not windows.drive
        and ".." not in posix.parts
        and posix.as_posix() == value
    )


def _sorted_unique(values: object) -> bool:
    return (
        isinstance(values, list)
        and all(isinstance(value, str) for value in values)
        and values == sorted(set(values))
    )


def validate_manifest_paths(manifest: Mapping) -> bool:
    """Validate every manifest path before any filesystem join occurs."""
    try:
        repositories = manifest["repositories"]
        snapshot = manifest["scope_snapshot"]
        candidates = snapshot["candidate_ids"]
        directories = [record["path"] for record in manifest["directories"]]
        files = [record["path"] for record in manifest["files"]]
        graph_paths = list(manifest["graph_signatures"])
        document_paths = list(manifest["document_digests"])
    except (KeyError, TypeError):
        return False
    def filesystem_candidate(value: object) -> bool:
        if not isinstance(value, str):
            return False
        if value.startswith("outside-root:"):
            suffix = value.removeprefix("outside-root:")
            return len(suffix) == 16 and all(
                character in "0123456789abcdef" for character in suffix
            )
        return is_normalized_relative_path(value, allow_root=True)
    if not (
        isinstance(repositories, list)
        and _sorted_unique(repositories)
        and all(
            is_normalized_relative_path(path, allow_root=True)
            for path in repositories
        )
        and isinstance(candidates, list)
        and _sorted_unique(candidates)
        and all(filesystem_candidate(path) for path in candidates)
        and _sorted_unique(directories)
        and all(
            is_normalized_relative_path(path, allow_root=True)
            for path in directories
        )
        and _sorted_unique(files)
        and all(is_normalized_relative_path(path) for path in files)
        and graph_paths == sorted(set(graph_paths))
        and all(
            is_normalized_relative_path(path, allow_root=True)
            for path in graph_paths
        )
        and set(graph_paths) == set(repositories)
        and document_paths == sorted(set(document_paths))
        and all(is_normalized_relative_path(path) for path in document_paths)
    ):
        return False
    map_evidence = snapshot.get("map")
    return (
        map_evidence is None
        or (
            isinstance(map_evidence, Mapping)
            and is_normalized_relative_path(map_evidence.get("path"))
        )
    )


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


def _issue(boundary: str, reason: str = "unreadable") -> dict:
    return {"boundary": boundary, "reason": reason}


def _config_identity(root: Path) -> tuple[str | None, dict | None]:
    for name in (".index.toml", ".repomap.toml"):
        path = root / name
        try:
            if not stat_module.S_ISREG(path.stat().st_mode):
                continue
        except FileNotFoundError:
            continue
        except OSError:
            return None, _issue("freshness.config")
        try:
            return (
                _sha256_bytes(
                    name.encode("utf-8") + b"\0" + path.read_bytes()
                ),
                None,
            )
        except FileNotFoundError:
            continue
        except OSError:
            return None, _issue("freshness.config")
    return _sha256_text("no-active-index-config"), None


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
    if (
        isinstance(evidence, Mapping)
        and is_normalized_relative_path(evidence.get("path"))
    ):
        relative = PurePosixPath(evidence["path"])
        return root.joinpath(*relative.parts)
    return root / "WORKSPACE-REPO-MAP.json"


def _map_evidence(
    root: Path, snapshot: Mapping
) -> tuple[dict | None, dict | None]:
    path = _map_path(root, snapshot)
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return None, _issue("freshness.workspace-map", "invalid-path")
    try:
        digest = _sha256_bytes(path.read_bytes())
    except FileNotFoundError:
        digest = "missing"
    except OSError:
        return None, _issue("freshness.workspace-map")
    return {"path": relative, "sha256": digest}, None


def _scan_repositories(root: Path, repositories, budget, *, strict: bool) -> dict:
    directories: list[dict] = []
    files: list[dict] = []
    graph_signatures: dict[str, str | None] = {}
    markdown_paths: list[str] = []
    markdown_set: set[str] = set()
    missing_repositories: list[str] = []
    evidence_error: dict | None = None
    drift = False
    complete = True

    for candidate in repositories:
        repo_id = candidate.id
        repo = candidate.path
        graph_entries: list[tuple[str, str]] = []
        if repo is None:
            graph_signatures[repo_id] = None
            missing_repositories.append(repo_id)
            continue
        try:
            repo_is_directory = stat_module.S_ISDIR(repo.stat().st_mode)
            (repo / ".git").stat()
        except FileNotFoundError:
            graph_signatures[repo_id] = None
            missing_repositories.append(repo_id)
            continue
        except OSError:
            graph_signatures[repo_id] = None
            evidence_error = evidence_error or _issue("manifest.repository")
            complete = False
            continue
        if not repo_is_directory:
            graph_signatures[repo_id] = None
            missing_repositories.append(repo_id)
            continue
        try:
            repo.relative_to(root)
        except ValueError:
            graph_signatures[repo_id] = None
            complete = False
            continue

        def walk_error(_error: OSError) -> None:
            nonlocal evidence_error, complete, drift
            if isinstance(_error, FileNotFoundError):
                drift = True
            else:
                evidence_error = evidence_error or _issue("manifest.walk")
            complete = False

        for dirpath, dirnames, filenames in os.walk(repo, onerror=walk_error):
            if not budget.checkpoint(
                "manifest.directory", counter="directories_visited"
            ):
                complete = False
                dirnames.clear()
                break
            directory = Path(dirpath)
            try:
                directories.append(_stat(directory, root))
            except FileNotFoundError:
                drift = True
                complete = False
                dirnames.clear()
                break
            except OSError:
                evidence_error = evidence_error or _issue(
                    "manifest.directory"
                )
                complete = False
                dirnames.clear()
                break
            except ValueError:
                drift = True
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
                except FileNotFoundError:
                    drift = True
                    complete = False
                    continue
                except OSError:
                    evidence_error = evidence_error or _issue("manifest.file")
                    complete = False
                    continue
                except ValueError:
                    drift = True
                    complete = False
                    continue
                record["graph"] = relevant
                record["markdown"] = markdown
                if relevant and strict:
                    try:
                        content_digest = _sha256_bytes(path.read_bytes())
                    except FileNotFoundError:
                        drift = True
                        complete = False
                        continue
                    except OSError:
                        evidence_error = evidence_error or _issue(
                            "manifest.content"
                        )
                        complete = False
                        continue
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
            _fold_pairs(graph_entries)
            if (
                strict
                and complete
                and not budget.exhausted
                and evidence_error is None
                and not drift
            )
            else None
        )
        if budget.exhausted:
            complete = False
            break

    for candidate in repositories[len(graph_signatures):]:
        graph_signatures[candidate.id] = None
    directories = list(
        {record["path"]: record for record in directories}.values()
    )
    files = list({record["path"]: record for record in files}.values())
    directories.sort(key=lambda item: item["path"])
    files.sort(key=lambda item: item["path"])
    return {
        "complete": complete and not budget.exhausted,
        "directories": directories,
        "files": files,
        "graph_signatures": graph_signatures,
        "markdown_paths": sorted(markdown_paths),
        "missing_repositories": missing_repositories,
        "evidence_error": evidence_error,
        "drift": drift,
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
    candidate_ids = snapshot.get("candidate_ids")
    if isinstance(candidate_ids, list):
        snapshot["candidate_ids"] = sorted(set(candidate_ids))
    map_error = None
    if snapshot.get("kind") in {"workspace-map", "map"}:
        map_evidence, map_error = _map_evidence(root, snapshot)
        snapshot["map"] = map_evidence
    config_id, config_error = _config_identity(root)
    evidence_error = (
        scan["evidence_error"] or map_error or config_error
    )

    markdown_paths = set(scan["markdown_paths"])
    document_digests: dict[str, str] = {}
    if strict and document_bodies:
        for path, body in sorted(document_bodies.items()):
            normalized = PurePosixPath(path)
            if (
                isinstance(path, str)
                and isinstance(body, str)
                and is_normalized_relative_path(path)
                and normalized.as_posix() in markdown_paths
            ):
                document_digests[normalized.as_posix()] = _sha256_text(body)

    markdown_signature = (
        _fold_paths(scan["markdown_paths"])
        if (
            strict
            and scan["complete"]
            and not scan["missing_repositories"]
            and not scan["drift"]
            and evidence_error is None
        )
        else None
    )
    strict_signature = (
        _strict_fold(
            scan["graph_signatures"], markdown_signature, document_digests
        )
        if (
            strict
            and scan["complete"]
            and not scan["missing_repositories"]
            and not scan["drift"]
            and evidence_error is None
        )
        else None
    )
    repository_ids = sorted(candidate.id for candidate in repositories)
    graph_signatures = {
        repo_id: scan["graph_signatures"][repo_id]
        for repo_id in repository_ids
    }
    return {
        "schema": MANIFEST_SCHEMA,
        "complete": (
            scan["complete"]
            and not scan["missing_repositories"]
            and not scan["drift"]
            and evidence_error is None
        ),
        "root_id": _root_id(root),
        "config_id": config_id,
        "scope_snapshot": snapshot,
        "repositories": repository_ids,
        "directories": scan["directories"],
        "files": scan["files"],
        "graph_signatures": graph_signatures,
        "markdown_paths_signature": markdown_signature,
        "document_digests": document_digests,
        "strict_signature": strict_signature,
        "last_strict_verified_at": time()
        if (
            strict
            and scan["complete"]
            and not scan["missing_repositories"]
            and not scan["drift"]
            and evidence_error is None
        )
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
    boundary: str | None = None,
    reason: str | None = None,
) -> dict:
    result = {
        "status": status,
        "checked": {key: max(0, value) for key, value in checked.items()},
        "unchecked": {key: max(0, value) for key, value in unchecked.items()},
        "exhausted_at": exhausted_at,
    }
    if boundary is not None:
        result["boundary"] = boundary
    if reason is not None:
        result["reason"] = reason
    return result


def _unknown(
    manifest: Mapping,
    budget,
    *,
    boundary: str | None = None,
    reason: str | None = None,
) -> dict:
    checked, unchecked = _counts(manifest)
    return _result(
        "UNKNOWN",
        checked,
        unchecked,
        exhausted_at=budget.exhausted_at,
        boundary=boundary,
        reason=reason,
    )


def _candidate_universe(
    root: Path, manifest: Mapping, budget, *, strict: bool
) -> tuple[str, dict | None]:
    snapshot = manifest.get("scope_snapshot")
    if not isinstance(snapshot, Mapping):
        return "DRIFT", None
    kind = snapshot.get("kind")
    if kind == "explicit":
        return "FRESH", None
    if not snapshot.get("complete", False):
        if kind not in {"workspace-map", "map"}:
            return "UNKNOWN", _issue(
                "freshness.candidate-universe", "incomplete"
            )
        map_evidence = snapshot.get("map")
        if not isinstance(map_evidence, Mapping):
            return "DRIFT", None
        current_map, map_error = _map_evidence(root, snapshot)
        if map_error is not None:
            return "UNKNOWN", map_error
        if current_map != dict(map_evidence):
            return "DRIFT", None
        return (
            ("UNKNOWN", _issue("freshness.candidate-universe", "incomplete"))
            if strict
            else ("FRESH", None)
        )
    if kind in {"workspace-map", "map"}:
        map_evidence = snapshot.get("map")
        if not isinstance(map_evidence, Mapping):
            return "DRIFT", None
        current_map, map_error = _map_evidence(root, snapshot)
        if map_error is not None:
            return "UNKNOWN", map_error
        if current_map != dict(map_evidence):
            return "DRIFT", None
    if kind not in {"discovery", "workspace-map", "map"}:
        return "DRIFT", None

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
        return "UNKNOWN", _issue("freshness.discovery")
    discovered_ids = sorted(
        path.relative_to(root).as_posix() or "." for path in discovered
    )
    cached_ids = sorted(snapshot.get("candidate_ids", ()))
    return (
        ("FRESH", None)
        if discovered_ids == cached_ids
        else ("DRIFT", None)
    )


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
            except FileNotFoundError:
                return _result("DRIFT", checked, unchecked)
            except OSError:
                return _result(
                    "UNKNOWN",
                    checked,
                    unchecked,
                    boundary=boundary,
                    reason="unreadable",
                )
            except (KeyError, TypeError, ValueError):
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
    if scan["drift"]:
        return _result("DRIFT", checked, unchecked)
    if scan["evidence_error"] is not None:
        return _result(
            "UNKNOWN",
            checked,
            unchecked,
            **scan["evidence_error"],
        )
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
        except FileNotFoundError:
            selected = False
        except (OSError, RuntimeError):
            return _result(
                "UNKNOWN",
                checked,
                unchecked,
                boundary="docs.open",
                reason="unreadable",
            )
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
            body = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _result("DRIFT", checked, unchecked)
        except (OSError, UnicodeError):
            return _result(
                "UNKNOWN",
                checked,
                unchecked,
                boundary="docs.open",
                reason="unreadable",
            )
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
        or not validate_manifest_paths(manifest)
        or manifest.get("root_id") != _root_id(root)
    ):
        checked, unchecked = _counts(manifest if isinstance(manifest, Mapping) else {})
        return _result("DRIFT", checked, unchecked)
    config_id, config_error = _config_identity(root)
    if config_error is not None:
        return _unknown(manifest, budget, **config_error)
    if manifest.get("config_id") != config_id:
        checked, unchecked = _counts(manifest)
        return _result("DRIFT", checked, unchecked)
    if not manifest.get("complete", False):
        return _unknown(
            manifest,
            budget,
            boundary="freshness.manifest",
            reason="incomplete",
        )
    universe, universe_error = _candidate_universe(
        root, manifest, budget, strict=strict
    )
    if universe == "DRIFT":
        checked, unchecked = _counts(manifest)
        return _result("DRIFT", checked, unchecked)
    if universe == "UNKNOWN":
        return _unknown(manifest, budget, **(universe_error or {}))
    if strict:
        return _validate_strict(root, manifest, budget)
    return _validate_stats(root, manifest, budget)
