"""Deterministic content fingerprints: detect when graph-relevant content changed.

A repo fingerprint is a SHA-256 over the sorted (relative-path, file-SHA-256)
pairs of every file a resolver could read (manifests and sources across all
nine ecosystems), so identical content yields an identical fingerprint on any
machine, and any graph-relevant edit, addition, or removal changes it. The
workspace fingerprint folds the per-repo fingerprints under their names.

It is conservative on purpose. It may report a change to a file that does not
alter the resolved graph (so STALE can be a false alarm), but it never misses
a change to a file that could (so FRESH is never a false assurance). The set
of relevant files is declared by the resolvers themselves
(`fingerprint_names`, `fingerprint_suffixes`, `fingerprint_globs`), so a new
resolver is covered without touching this module.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

from ..graph.resolvers import ALL_RESOLVERS
from ..graph.walk import EXCLUDE_DIRS

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


def relevant_files(repo_root: Path, resolvers=ALL_RESOLVERS) -> Iterator[Path]:
    """Yield every graph-relevant file under repo_root (the manifests and source
    suffixes the resolvers read, across all ecosystems), pruning EXCLUDE_DIRS.
    Fail-closed: a missing or unreadable tree yields nothing rather than raising.
    """
    names, suffixes, globs = _matchers(resolvers)
    for dirpath, dirnames, filenames in os.walk(Path(repo_root), onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if _is_relevant(fn, names, suffixes, globs):
                yield Path(dirpath) / fn


def repo_fingerprint(repo_root: Path, resolvers=ALL_RESOLVERS) -> str:
    """A SHA-256 over the sorted (relpath, file-sha256) of every relevant file.

    Fail-closed: an unreadable file contributes a fixed marker rather than
    raising, and a missing or unreadable tree yields the empty-set hash.
    """
    root = Path(repo_root)
    entries: list[tuple[str, str]] = []
    for p in relevant_files(root, resolvers):
        try:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            digest = "unreadable"
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        entries.append((rel, digest))
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
