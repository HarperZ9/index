"""Filesystem walk that prunes heavy/irrelevant dirs and never raises on I/O."""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "venvs", "node_modules", "site-packages", "__pycache__",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "build", "dist", ".eggs", ".cache", ".playwright-mcp",
    ".warden-safe-cache", ".next", ".turbo",
    "target", "coverage", ".coverage", ".nyc_output",
    ".parcel-cache", ".svelte-kit", ".angular", ".expo",
    ".gradle", ".idea", ".vscode", ".yarn", ".pnpm-store",
    ".terraform", "out",
})

Checkpoint = Callable[[str], bool]
_ACTIVE_CHECKPOINT: ContextVar[Checkpoint | None] = ContextVar(
    "index_graph_walk_checkpoint", default=None
)


@contextmanager
def walk_budget(checkpoint: Checkpoint | None):
    token = _ACTIVE_CHECKPOINT.set(checkpoint)
    try:
        yield
    finally:
        _ACTIVE_CHECKPOINT.reset(token)


def _continue(boundary: str) -> bool:
    checkpoint = _ACTIVE_CHECKPOINT.get()
    return checkpoint is None or checkpoint(boundary)


def walk_files(root: Path, suffixes: tuple[str, ...] | None = None,
               names: tuple[str, ...] | None = None) -> Iterator[Path]:
    """Yield files under `root`, pruning EXCLUDE_DIRS; fail-closed on OSError.

    Match by `suffixes` (e.g. (".py",)) or exact `names` (e.g. ("__main__.py",)).
    A missing/unreadable root yields nothing rather than raising.
    """
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        if not _continue("graph.walk.directory"):
            return
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for fn in sorted(filenames):
            if names is not None and fn in names:
                if not _continue("graph.walk.file"):
                    return
                yield Path(dirpath) / fn
            elif suffixes is not None and fn.endswith(suffixes):
                if not _continue("graph.walk.file"):
                    return
                yield Path(dirpath) / fn
