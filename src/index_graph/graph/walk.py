"""Pruned filesystem walks; complete graph scopes fail on source I/O errors."""
from __future__ import annotations

import fnmatch
import hashlib
import io
import os
import threading
from contextlib import contextmanager
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "venvs", "node_modules", "site-packages", "lib64", "__pycache__",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "build", "dist", ".eggs", ".cache", ".playwright-mcp",
    ".warden-safe-cache", ".next", ".turbo",
    "target", "coverage", ".coverage", ".nyc_output",
    ".parcel-cache", ".svelte-kit", ".angular", ".expo",
    ".gradle", ".idea", ".vscode", ".yarn", ".pnpm-store",
    ".terraform", "out",
})

_LOCAL = threading.local()
_SOURCE_CACHE_MAX_BYTES = 16 * 1024 * 1024
_SOURCE_CACHE_MAX_FILES = 4096
_SOURCE_DIGEST_JOURNAL_MAX_ENTRIES = 100_000


class GraphSourceError(RuntimeError):
    """A complete graph cannot be derived because a source could not be read."""


@dataclass(frozen=True)
class DirectoryMembershipSnapshot:
    path: Path
    entries: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PreloadedFileListing:
    files: tuple[Path, ...]
    directory_snapshots: tuple[DirectoryMembershipSnapshot, ...] = ()


PreloadedFileValue = Sequence[Path | str] | PreloadedFileListing


def _source_error(operation: str, path: Path, error: OSError) -> None:
    if getattr(_LOCAL, "file_cache", None) is not None:
        _LOCAL.source_reuse_complete = False
        # Do not copy raw OS diagnostics or absolute private paths into receipts.
        raise GraphSourceError(
            f"graph source {operation} failed: {path.name!r} ({type(error).__name__})"
        ) from None


def _walk_error(error: OSError) -> None:
    _source_error("traversal", Path(error.filename) if error.filename else Path("source"), error)


def _directory_entry_kind(entry: os.DirEntry) -> str:
    try:
        if entry.is_dir(follow_symlinks=False):
            return "dir"
        if entry.is_file(follow_symlinks=False):
            return "file"
    except OSError:
        return "unreadable"
    return "other"


def directory_membership_from_walk(
    path: Path,
    dirnames: Sequence[str],
    filenames: Sequence[str],
) -> DirectoryMembershipSnapshot:
    entries = [(name, "dir") for name in dirnames]
    entries.extend((name, "file") for name in filenames)
    return DirectoryMembershipSnapshot(
        path=Path(path).resolve(),
        entries=tuple(sorted(entries, key=lambda item: (item[0].lower(), item[0], item[1]))),
    )


def _scan_directory_membership(path: Path) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    with os.scandir(path) as scanner:
        for entry in scanner:
            entries.append((entry.name, _directory_entry_kind(entry)))
    return tuple(sorted(entries, key=lambda item: (item[0].lower(), item[0], item[1])))


def _preloaded_is_current(listing: PreloadedFileListing) -> bool:
    for snapshot in listing.directory_snapshots:
        try:
            current = _scan_directory_membership(snapshot.path)
        except OSError:
            return False
        if current != snapshot.entries:
            return False
    return True


def _preloaded_file_listing(value: PreloadedFileValue) -> PreloadedFileListing:
    if isinstance(value, PreloadedFileListing):
        return value
    return PreloadedFileListing(tuple(Path(path) for path in value))


def _preloaded_file_cache(
    file_lists: Mapping[Path | str, PreloadedFileValue] | None,
) -> dict[str, PreloadedFileListing]:
    if not file_lists:
        return {}
    return {
        str(Path(root).resolve()): _preloaded_file_listing(paths)
        for root, paths in file_lists.items()
    }


@contextmanager
def cached_file_scope(file_lists: Mapping[Path | str, PreloadedFileValue] | None = None):
    """Share one pruned filesystem listing across resolver walks in one repo build."""
    previous = getattr(_LOCAL, "file_cache", None)
    preloaded = _preloaded_file_cache(file_lists)
    if previous is None:
        _LOCAL.file_cache = dict(preloaded)
        _LOCAL.source_cache = {}
        _LOCAL.source_digest_journal = {}
        _LOCAL.source_cache_bytes = 0
        _LOCAL.source_reuse_complete = True
    elif preloaded:
        _LOCAL.file_cache = {**previous, **preloaded}
    try:
        yield
    finally:
        if previous is None:
            try:
                delattr(_LOCAL, "file_cache")
                delattr(_LOCAL, "source_cache")
                delattr(_LOCAL, "source_digest_journal")
                delattr(_LOCAL, "source_cache_bytes")
                delattr(_LOCAL, "source_reuse_complete")
            except AttributeError:
                pass
        else:
            _LOCAL.file_cache = previous


def _record_unretained_source_read(key: str, data: bytes) -> None:
    """Track consistency for source bytes that are too large to retain.

    The journal holds path digests, not file bodies. It is still bounded because
    very large repositories can exceed byte and file retention at the same time.
    If the journal bound is exceeded, persistent cache is disabled for the build
    while source coverage continues from the bytes that were read.
    """
    journal = getattr(_LOCAL, "source_digest_journal", None)
    if journal is None:
        _LOCAL.source_reuse_complete = False
        return
    digest = hashlib.sha256(data).hexdigest()
    previous = journal.get(key)
    if previous is None:
        if len(journal) >= _SOURCE_DIGEST_JOURNAL_MAX_ENTRIES:
            _LOCAL.source_reuse_complete = False
            return
        journal[key] = digest
    elif previous != digest:
        _LOCAL.source_reuse_complete = False


def read_source_bytes(path: Path) -> bytes:
    """Reuse exact working bytes only within a build, with bounded memory.

    This never trusts Git metadata or a previous process's source bytes. Files
    beyond the memory/file limit are read normally; coverage is unchanged. Their
    first-read digest is journaled so repeated resolver reads can still prove
    they saw the same bytes before the derived build is written to disk cache.
    """
    cache = getattr(_LOCAL, "source_cache", None)
    key = str(path.absolute())
    if cache is not None and key in cache:
        return cache[key]
    try:
        data = path.read_bytes()
    except OSError as error:
        _source_error("read", path, error)
        raise
    if cache is not None:
        can_retain = (len(cache) < _SOURCE_CACHE_MAX_FILES
                      and _LOCAL.source_cache_bytes + len(data) <= _SOURCE_CACHE_MAX_BYTES)
        # Check previously journaled bytes even if this read now fits the byte
        # cache. A file can shrink between fingerprinting and resolver parsing.
        if key in _LOCAL.source_digest_journal or not can_retain:
            _record_unretained_source_read(key, data)
        if can_retain:
            cache[key] = data
            _LOCAL.source_cache_bytes += len(data)
    return data


def source_reuse_complete() -> bool:
    """Whether shared source reads remain consistent enough for cache persistence."""
    return getattr(_LOCAL, "source_reuse_complete", False)


def read_source_text(path: Path, *, encoding="utf-8", errors="replace") -> str:
    # TextIOWrapper preserves Path.read_text's universal-newline behavior.
    with io.TextIOWrapper(io.BytesIO(read_source_bytes(path)),
                          encoding=encoding, errors=errors) as stream:
        return stream.read()


def _matches(filename: str, suffixes: tuple[str, ...] | None,
             names: tuple[str, ...] | None,
             globs: tuple[str, ...] | None = None) -> bool:
    if names is not None and filename in names:
        return True
    if suffixes is not None and filename.endswith(suffixes):
        return True
    return globs is not None and any(fnmatch.fnmatchcase(filename, g) for g in globs)


def _scoped_all_files(root: Path, checkpoint=None) -> list[Path]:
    """All local files under existing pruning and nested repository boundaries.

    Do not use Git ignore rules or index metadata here: ignored and index-hidden
    working files can contain dependencies. Cache only inside one repo build.
    """
    key = str(root.resolve())
    cache = getattr(_LOCAL, "file_cache", None)
    if cache is not None and key in cache:
        cached = cache[key]
        if isinstance(cached, PreloadedFileListing):
            if _preloaded_is_current(cached):
                files = list(cached.files)
                cache[key] = files
                return files
            del cache[key]
        else:
            return cached
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=_walk_error):
        current = Path(dirpath)
        if checkpoint is not None and not checkpoint(current):
            # An interrupted listing is never reusable as a complete scope.
            return out
        if current != root and (".git" in dirnames or ".git" in filenames):
            dirnames[:] = []
            continue
        dirnames[:] = sorted((d for d in dirnames if d not in EXCLUDE_DIRS), key=str.lower)
        out.extend(current / filename for filename in sorted(filenames))
    if cache is not None:
        cache[key] = out
    return out


def walk_files(root: Path, suffixes: tuple[str, ...] | None = None,
               names: tuple[str, ...] | None = None,
               checkpoint=None,
               globs: tuple[str, ...] | None = None,
               stop_at_nested_repos: bool = False) -> Iterator[Path]:
    """Yield files under `root`, pruning EXCLUDE_DIRS.

    Match by `suffixes` (e.g. (".py",)) or exact `names` (e.g. ("__main__.py",)).
    Outside graph-build scopes, a missing/unreadable root yields nothing. Inside
    a scoped graph build, traversal errors raise GraphSourceError so omitted
    sources cannot become a successful complete graph or cached file listing.

    When `stop_at_nested_repos` is true, a child directory with a .git marker is
    treated as a separate repository boundary. The root itself is still scanned.
    """
    root = Path(root)
    if stop_at_nested_repos:
        for path in _scoped_all_files(root, checkpoint=checkpoint):
            if checkpoint is not None and not checkpoint(path.parent):
                break
            if _matches(path.name, suffixes, names, globs):
                yield path
        return

    for dirpath, dirnames, filenames in os.walk(root, onerror=_walk_error):
        current = Path(dirpath)
        if checkpoint is not None and not checkpoint(current):
            dirnames[:] = []
            break
        dirnames[:] = sorted((d for d in dirnames if d not in EXCLUDE_DIRS), key=str.lower)
        for fn in filenames:
            if _matches(fn, suffixes, names, globs):
                yield Path(dirpath) / fn
