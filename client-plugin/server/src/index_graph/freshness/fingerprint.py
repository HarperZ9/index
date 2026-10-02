"""Deterministic content fingerprints: detect when graph-relevant content changed.

A repo fingerprint is a SHA-256 over the sorted relative path and content SHA-256
for every file a resolver could read (manifests and sources across all nine
ecosystems), so identical content yields an identical fingerprint on any machine,
and any graph-relevant edit, addition, or removal changes it. Working bytes are
always read: Git index flags and clean filters can hide resolver-visible edits.
The workspace fingerprint folds the per-repo fingerprints under their names.

It is conservative on purpose. It may report a change to a file that does not
alter the resolved graph (so STALE can be a false alarm), but it never misses
a change to a file that could (so FRESH is never a false assurance). The set
of relevant files is declared by the resolvers themselves
(`fingerprint_names`, `fingerprint_suffixes`, `fingerprint_globs`), so a new
resolver is covered without touching this module.
"""
from __future__ import annotations

import hashlib
import fnmatch
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter

from ..graph.resolvers import ALL_RESOLVERS
from ..graph.walk import read_source_bytes, walk_files

SCHEMA = "index.freshness/1"


def _matchers(resolvers):
    names: set[str] = set()
    suffixes: set[str] = set()
    globs: set[str] = set()
    for r in resolvers:
        names |= set(getattr(r, "fingerprint_names", ()))
        suffixes |= set(getattr(r, "fingerprint_suffixes", ()))
        globs |= set(getattr(r, "fingerprint_globs", ()))
    return names, tuple(sorted(suffixes)), tuple(sorted(globs))


def _is_relevant(filename: str, names, suffixes, globs) -> bool:
    if filename in names:
        return True
    if suffixes and filename.endswith(suffixes):
        return True
    # fnmatchcase, not fnmatch: fnmatch lowercases via os.path.normcase on
    # Windows, which would make the fingerprint platform-dependent.
    return any(fnmatch.fnmatchcase(filename, g) for g in globs)


def _add_stat(stats: dict[str, int] | None, key: str, value: int) -> None:
    if stats is not None:
        stats[key] = int(stats.get(key, 0)) + int(value)


def _add_timing(stats: dict[str, int] | None, key: str, started: float) -> None:
    _add_stat(stats, key, int((perf_counter() - started) * 1000))


def relevant_files(repo_root: Path, resolvers=ALL_RESOLVERS, *, checkpoint=None,
                   stop_at_nested_repos: bool = False) -> Iterator[Path]:
    """Yield every graph-relevant file under repo_root (the manifests and source
    suffixes the resolvers read, across all ecosystems), pruning EXCLUDE_DIRS.
    Fail-closed: a missing or unreadable tree yields nothing rather than raising.
    When `stop_at_nested_repos` is true, child repositories are excluded so a
    parent repo fingerprint matches the graph builder's repository boundary.
    """
    names, suffixes, globs = _matchers(resolvers)
    yield from walk_files(
        Path(repo_root),
        names=tuple(sorted(names)) or None,
        suffixes=suffixes or None,
        globs=globs or None,
        checkpoint=checkpoint,
        stop_at_nested_repos=stop_at_nested_repos,
    )


def repo_fingerprint(repo_root: Path, resolvers=ALL_RESOLVERS, *, stats: dict[str, int] | None = None) -> str:
    """A SHA-256 over the sorted (relpath, file-sha256) of every relevant file.

    Fail-closed: an unreadable file contributes a fixed marker rather than
    raising, and a missing or unreadable tree yields the empty-set hash.
    """
    root = Path(repo_root)
    entries = []
    started = perf_counter()
    files = list(relevant_files(root, resolvers, stop_at_nested_repos=True))
    _add_timing(stats, "fingerprint_walk_ms", started)
    _add_stat(stats, "fingerprint_files", len(files))
    started = perf_counter()
    byte_count = 0
    unreadable = 0
    for p in files:
        try:
            data = read_source_bytes(p)
            byte_count += len(data)
            digest = hashlib.sha256(data).hexdigest()
        except OSError:
            unreadable += 1
            digest = "unreadable"
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        entries.append((rel, digest))
    _add_stat(stats, "fingerprint_bytes", byte_count)
    _add_stat(stats, "fingerprint_unreadable", unreadable)
    _add_timing(stats, "fingerprint_read_hash_ms", started)
    entries.sort()
    h = hashlib.sha256()
    for rel, digest in entries:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(digest.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def workspace_fingerprint(repo_paths: dict[str, Path], resolvers=ALL_RESOLVERS) -> dict:
    """An index.freshness/1 stamp: a per-repo fingerprint map plus a root fold."""
    repos = {name: repo_fingerprint(root, resolvers)
             for name, root in sorted(repo_paths.items())}
    h = hashlib.sha256()
    for name in sorted(repos):
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(repos[name].encode("ascii"))
        h.update(b"\n")
    return {"schema": SCHEMA, "root": h.hexdigest(), "repos": repos}
