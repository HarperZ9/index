"""Discovery, parallel git fan-out, and map assembly."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from .classify import classify
from .config import Config
from .gitmeta import canonical_path_identity, gitfile_backlink_matches, repo_metadata
from .model import SCHEMA_VERSION, Map, RepoRow


def _warn(message: str) -> None:
    try:
        print(message, file=sys.stderr)
    except UnicodeError:
        safe = message.encode("utf-8", "backslashreplace").decode("ascii", "replace")
        print(safe, file=sys.stderr)


def _alias_rank(path: Path) -> tuple[bool, str, str]:
    lexical = os.path.normcase(os.path.abspath(path))
    return (lexical != canonical_path_identity(path), lexical, str(path))


def deduplicate_repo_aliases(repos: Iterable[Path]) -> list[Path]:
    selected: dict[str, Path] = {}
    for repo in repos:
        identity = canonical_path_identity(repo)
        incumbent = selected.get(identity)
        if incumbent is None or _alias_rank(repo) < _alias_rank(incumbent):
            selected[identity] = repo
    return sorted(selected.values(), key=lambda path: (str(path).casefold(), str(path)))


def discover_repos(root: Path, config: Config) -> list[Path]:
    prune = config.prune
    repos: set[Path] = set()
    def _onerror(exc: OSError) -> None:
        _warn(f"warning: skipped unreadable directory during repo discovery: {exc}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=_onerror):
        current = Path(dirpath)
        if ".git" in dirnames or ".git" in filenames:
            repos.add(current)
        dirnames[:] = [name for name in dirnames if name not in prune]
    valid: list[Path] = []
    for repo in sorted(repos, key=lambda p: p.relative_to(root).as_posix().lower()):
        if not gitfile_backlink_matches(repo):
            rel = _relative(repo, root)
            _warn(
                "warning: skipped unregistered linked-worktree copy "
                f"{rel}; run 'git worktree repair' if this worktree was moved intentionally"
            )
            continue
        valid.append(repo)
    return deduplicate_repo_aliases(valid)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return path.name


def _repo_row(repo: Path, root: Path, config: Config) -> RepoRow:
    meta = repo_metadata(repo)
    rel = _relative(repo, root)
    class_ = classify(rel, True, meta["origin"], config)
    origin = "" if class_ in config.omit_origin_classes else meta["origin"]
    path = rel if config.portable else str(repo)
    markers = tuple(name for name in config.markers if (repo / name).exists())
    return RepoRow(
        path=path, class_=class_, branch=meta["branch"], head=meta["head"],
        origin=origin, dirty_count=meta["dirty_count"],
        untracked_count=meta["untracked_count"], markers=markers,
    )


def _safe_repo_row(repo: Path, root: Path, config: Config) -> RepoRow:
    # Spec §9: one repo's failure must degrade to a row, never crash the scan.
    try:
        return _repo_row(repo, root, config)
    except Exception as exc:
        rel = _relative(repo, root)
        _warn(f"warning: failed to scan {rel}: {exc}")
        return RepoRow(
            path=(rel if config.portable else str(repo)), class_="unknown",
            branch="unknown", head="unknown", origin="", dirty_count=0,
            untracked_count=0, markers=(),
        )


def _top_level(root: Path, config: Config) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if path.name == ".git":
            continue
        try:
            stat = path.stat()
            is_dir = path.is_dir()
        except OSError as exc:
            _warn(f"warning: skipped top-level entry {path.name}: {exc}")
            continue
        entries.append({
            "name": path.name,
            "kind": "directory" if is_dir else "file",
            "class": classify(path.name, False, "", config),
            "bytes": None if is_dir else stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        })
    return entries


def build_map(root: Path, config: Config, tool_version: str) -> Map:
    root = root.resolve()
    repo_paths = discover_repos(root, config)
    # Executor.map preserves submission order, so rows stay in discovery (sorted) order
    # regardless of thread completion order; output is deterministic.
    with ThreadPoolExecutor(max_workers=config.jobs) as pool:
        rows = list(pool.map(lambda p: _safe_repo_row(p, root, config), repo_paths))
    class_counts: dict[str, int] = {}
    for row in rows:
        class_counts[row.class_] = class_counts.get(row.class_, 0) + 1
    return Map(
        schema_version=SCHEMA_VERSION,
        tool_version=tool_version,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        root_sha256_prefix=hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16],
        root=None if config.portable else str(root),
        absolute_paths_included=not config.portable,
        repo_count=len(rows),
        dirty_count=sum(row.dirty_count for row in rows),
        class_counts=class_counts,
        top_level=tuple(_top_level(root, config)),
        repositories=tuple(rows),
        annotations=dict(config.annotations),
    )


def write_map(root: Path, config: Config, tool_version: str, output: Path) -> Map:
    data = build_map(root, config, tool_version)
    output.write_text(json.dumps(data.to_json(), indent=2) + "\n", encoding="utf-8")
    return data
