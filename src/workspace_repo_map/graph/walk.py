"""Filesystem walk that prunes heavy/irrelevant dirs and never raises on I/O."""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "node_modules", "site-packages", "__pycache__", ".tox",
    ".mypy_cache", ".pytest_cache", "build", "dist", ".eggs",
})


def walk_files(root: Path, suffixes: tuple[str, ...] | None = None,
               names: tuple[str, ...] | None = None) -> Iterator[Path]:
    """Yield files under `root`, pruning EXCLUDE_DIRS; fail-closed on OSError.

    Match by `suffixes` (e.g. (".py",)) or exact `names` (e.g. ("__main__.py",)).
    A missing/unreadable root yields nothing rather than raising.
    """
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if names is not None and fn in names:
                yield Path(dirpath) / fn
            elif suffixes is not None and fn.endswith(suffixes):
                yield Path(dirpath) / fn
