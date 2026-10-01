"""Operation-local router inventory for shared traversal work."""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from .config import Config, load_config
from .graph.walk import (
    DirectoryMembershipSnapshot,
    EXCLUDE_DIRS,
    PreloadedFileListing,
    directory_membership_from_walk,
)
from .knowledge.docs import _MD_SUFFIXES
from .scan import (
    ScanBudget,
    ScanBudgetExceeded,
    enforce_interactive_repo_limit,
    repo_key_map,
    _warn,
)


class RouterInventoryInterrupted(RuntimeError):
    """Raised when inventory traversal is cooperatively interrupted."""

    def __init__(self, *, root: Path, path: Path):
        self.root = Path(root)
        self.path = Path(path)
        super().__init__(f"router inventory interrupted at {self.path.name!r}")


@dataclass(frozen=True)
class RouterInventory:
    root: Path
    repo_paths: dict[str, Path]
    repo_dirs: dict[str, str]
    repo_file_lists: dict[str, PreloadedFileListing]
    router_doc_paths: tuple[Path, ...]
    skipped: tuple[str, ...]
    stats: dict[str, int]


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return path.name


def _rel_to_root(root: Path, path: Path) -> str:
    rel = path.relative_to(root).as_posix()
    return "" if rel == "." else rel


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _walk_ancestors(path: Path, root: Path):
    current = path
    while True:
        yield current
        if current == root:
            return
        parent = current.parent
        if parent == current:
            return
        current = parent


def _nearest_ancestor(path: Path, candidates: set[Path], root: Path) -> Path | None:
    for current in _walk_ancestors(path, root):
        if current in candidates:
            return current
    return None


def _inside_config_prune(path: Path, root: Path, prune: frozenset[str]) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    return any(part in prune for part in parts)


def _blocked_by_repo_boundary(repo: Path, root: Path, repo_markers: set[Path], config: Config) -> bool:
    if config.descend_into_repos:
        return False
    for marker in repo_markers:
        if marker in {repo, root}:
            continue
        if _is_relative_to(repo, marker):
            return True
    return False


def _discover_repo_paths(
    root: Path,
    repo_markers: set[Path],
    config: Config,
    *,
    budget: ScanBudget,
    skipped: list[str],
) -> dict[str, Path]:
    repos = [
        repo
        for repo in repo_markers
        if not _inside_config_prune(repo, root, config.prune)
        and not _blocked_by_repo_boundary(repo, root, repo_markers, config)
    ]
    if budget.exhausted:
        raise ScanBudgetExceeded(root=root, budget=budget, repo_count=len(repos), skipped=skipped)
    repos = sorted(set(repos), key=lambda path: path.relative_to(root).as_posix().lower())
    keyed = repo_key_map(root, repos, include_root_repo=config.include_root_repo)
    enforce_interactive_repo_limit(len(keyed), budget_ms=budget.budget_ms)
    return keyed


def _assign_repo_file_lists(
    root: Path,
    files: list[Path],
    directory_snapshots: dict[Path, DirectoryMembershipSnapshot],
    repo_paths: dict[str, Path],
    repo_markers: set[Path],
    unreadable_dirs: list[Path],
) -> tuple[dict[str, PreloadedFileListing], int]:
    repo_by_root = {path: name for name, path in repo_paths.items()}
    repo_roots = set(repo_by_root)
    physical_roots = {
        name: directory_snapshots[path].path for name, path in repo_paths.items()
    }
    physical_markers = {directory_snapshots[path].path for path in repo_markers}
    buckets: dict[str, list[Path]] = {name: [] for name in repo_paths}
    seal_buckets: dict[str, dict[Path, DirectoryMembershipSnapshot]] = {
        name: {} for name in repo_paths
    }
    repo_error_names: set[str] = set()

    for error_dir in unreadable_dirs:
        owner = _nearest_ancestor(error_dir, repo_roots, root)
        if owner is None:
            continue
        boundary = _nearest_ancestor(error_dir, repo_markers, root)
        if boundary is None or boundary == owner:
            repo_error_names.add(repo_by_root[owner])

    for path in files:
        owner = _nearest_ancestor(path.parent, repo_roots, root)
        if owner is None:
            continue
        boundary = _nearest_ancestor(path.parent, repo_markers, root)
        if boundary is not None and boundary != owner:
            continue
        name = repo_by_root[owner]
        if name not in repo_error_names:
            physical_path = directory_snapshots[path.parent].path / path.name
            physical_owner = _nearest_ancestor(physical_path.parent, physical_markers, physical_roots[name])
            if (physical_owner == physical_roots[name]
                    and _is_relative_to(physical_path, physical_roots[name])):
                buckets[name].append(physical_path)

    for directory, snapshot in directory_snapshots.items():
        owner = _nearest_ancestor(directory, repo_roots, root)
        if owner is None:
            continue
        boundary = _nearest_ancestor(directory, repo_markers, root)
        if boundary is None or boundary == owner or directory == boundary:
            name = repo_by_root[owner]
            physical_boundary = _nearest_ancestor(snapshot.path, physical_markers, physical_roots[name])
            if (name not in repo_error_names
                    and _is_relative_to(snapshot.path, physical_roots[name])
                    and physical_boundary in {physical_roots[name], snapshot.path}):
                seal_buckets[name][directory] = snapshot

    for marker in repo_markers:
        parent_owner = _nearest_ancestor(marker.parent, repo_roots, root)
        if parent_owner is None or parent_owner == marker:
            continue
        parent_name = repo_by_root[parent_owner]
        snapshot = directory_snapshots.get(marker)
        if (snapshot is not None and parent_name not in repo_error_names
                and _is_relative_to(snapshot.path, physical_roots[parent_name])):
            seal_buckets[parent_name][marker] = snapshot

    return {
        name: PreloadedFileListing(
            files=tuple(paths),
            captured_root=physical_roots[name],
            directory_snapshots=tuple(
                snapshot
                for _path, snapshot in sorted(
                    seal_buckets[name].items(),
                    key=lambda item: _relative(item[0], root),
                )
            ),
        )
        for name, paths in buckets.items()
        if name not in repo_error_names
    }, len(repo_error_names)


def build_router_inventory(
    root: Path | str,
    *,
    config: Config | None = None,
    budget_ms: int | None = None,
    checkpoint: Callable[[Path], bool] | None = None,
) -> RouterInventory:
    """Walk once and derive router docs plus graph-scoped repo file listings.

    This is a traversal cache only. Source freshness continues to come from the
    exact bytes read by graph fingerprints and resolvers after this inventory is
    handed to `build_graph`.
    """
    root = Path(root).resolve()
    config = config or load_config(None, root)
    budget = ScanBudget(budget_ms)
    files: list[Path] = []
    doc_paths: list[Path] = []
    repo_markers: set[Path] = set()
    skipped: list[str] = []
    unreadable_dirs: list[Path] = []
    directory_snapshots: dict[Path, DirectoryMembershipSnapshot] = {}
    stats = {
        "physical_walks": 1,
        "physical_dirs": 0,
        "physical_files": 0,
        "physical_file_bytes": 0,
        "physical_stat_unreadable": 0,
        "traversal_ms": 0,
        "repo_count": 0,
        "router_doc_paths": 0,
        "repo_file_paths": 0,
        "repo_inventory_fallbacks": 0,
    }

    def onerror(exc: OSError) -> None:
        raw = getattr(exc, "filename", None)
        path = Path(raw) if raw else root
        if not path.is_absolute():
            path = root / path
        unreadable_dirs.append(path)
        skipped.append(str(raw or path))
        _warn(f"warning: skipped unreadable directory during router inventory: {exc}")

    started = perf_counter()
    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        # Keep the workspace spelling: resolving a junction can move this path
        # outside root and break relative repository keys and document routes.
        current = Path(dirpath)
        if checkpoint is not None and not checkpoint(current):
            skipped.append(f"router-inventory-checkpoint-rejected:{current}")
            dirnames[:] = []
            raise RouterInventoryInterrupted(root=root, path=current)
        if budget.budget_ms > 0 and not budget.checkpoint(current):
            skipped.append(f"scan-budget-exhausted:{current}")
            _warn(f"warning: router inventory budget exhausted at {current}")
            dirnames[:] = []
            break

        stats["physical_dirs"] += 1
        directory_snapshots[current] = directory_membership_from_walk(current, dirnames, filenames)
        if ".git" in dirnames or ".git" in filenames:
            repo_markers.add(current)

        dirnames[:] = sorted((name for name in dirnames if name not in EXCLUDE_DIRS), key=str.lower)
        for filename in sorted(filenames):
            path = current / filename
            files.append(path)
            stats["physical_files"] += 1
            try:
                stats["physical_file_bytes"] += path.stat().st_size
            except OSError:
                stats["physical_stat_unreadable"] += 1
            if filename.endswith(_MD_SUFFIXES):
                doc_paths.append(path)
    stats["traversal_ms"] = int((perf_counter() - started) * 1000)

    repo_paths = _discover_repo_paths(root, repo_markers, config, budget=budget, skipped=skipped)
    repo_dirs = {name: _rel_to_root(root, path) for name, path in repo_paths.items()}
    repo_file_lists, fallback_count = _assign_repo_file_lists(
        root,
        files,
        directory_snapshots,
        repo_paths,
        repo_markers,
        unreadable_dirs,
    )
    stats["repo_count"] = len(repo_paths)
    stats["router_doc_paths"] = len(doc_paths)
    stats["repo_file_paths"] = sum(len(listing.files) for listing in repo_file_lists.values())
    stats["repo_inventory_fallbacks"] = fallback_count

    return RouterInventory(
        root=root,
        repo_paths=repo_paths,
        repo_dirs=repo_dirs,
        repo_file_lists=repo_file_lists,
        router_doc_paths=tuple(sorted(doc_paths, key=lambda path: _relative(path, root))),
        skipped=tuple(skipped),
        stats=stats,
    )
