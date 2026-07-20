"""Deterministic, bounded document selection for already-scoped repositories."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..graph.walk import EXCLUDE_DIRS
from ..knowledge.docs import Doc, _parse_doc
from .budget import WorkBudget
from .model import reconcile_route, route_item
from .reads import DocumentReader
from .scope import RepoCandidate


_TOKEN = re.compile(r"[0-9a-z]+")
_DOC_SUFFIXES = (".md", ".markdown")


@dataclass(frozen=True)
class DocumentResult:
    docs: tuple[Doc, ...]
    candidates: tuple[str, ...]
    rejected: tuple[dict, ...]
    omitted: tuple[dict, ...]
    complete: bool
    reconciliation: dict


def _rank(path: str, query: str) -> tuple:
    tokens = set(_TOKEN.findall(query.lower()))
    score = sum(token in path.lower() for token in tokens)
    readme = Path(path).name.lower() == "readme.md"
    return (-score, -int(readme), path)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def select_documents(
    root: Path | str,
    repositories: Iterable[RepoCandidate],
    query: str,
    max_docs: int,
    budget: WorkBudget,
    *,
    reader: DocumentReader | None = None,
) -> DocumentResult:
    """Select parsed markdown only from the supplied repository scope."""
    if max_docs < 0:
        raise ValueError("max_docs must be >= 0")
    root_path = Path(root).resolve()
    if reader is not None:
        if reader.root != root_path:
            raise ValueError("reader root must match root")
        if reader.max_docs != max_docs:
            raise ValueError("reader max_docs must match max_docs")
        if reader.budget is not budget:
            raise ValueError("reader budget must match budget")
    active_reader = reader or DocumentReader(root_path, max_docs, budget)
    candidates: list[str] = []
    seen_candidates: set[str] = set()
    outside_selected: set[str] = set()
    enumeration_complete = True
    enumeration_boundary: str | None = None

    for repository in sorted(
        (item for item in repositories if item.path is not None),
        key=lambda item: item.id,
    ):
        assert repository.path is not None
        repository_path = repository.path.resolve()
        if not _is_within(repository_path, root_path):
            continue

        def onerror(_: OSError) -> None:
            nonlocal enumeration_complete, enumeration_boundary
            enumeration_complete = False
            enumeration_boundary = enumeration_boundary or "docs.enumeration.error"

        stop = False
        for dirpath, dirnames, filenames in os.walk(repository_path, onerror=onerror):
            if not budget.checkpoint(
                "docs.directory", counter="directories_visited"
            ):
                enumeration_complete = False
                enumeration_boundary = budget.exhausted_at
                stop = True
                break
            dirnames[:] = sorted(
                name for name in dirnames if name not in EXCLUDE_DIRS
            )
            for filename in sorted(filenames):
                if filename.lower().endswith(_DOC_SUFFIXES):
                    path = Path(dirpath) / filename
                    rel_path = path.relative_to(root_path).as_posix()
                    if rel_path in seen_candidates:
                        continue
                    seen_candidates.add(rel_path)
                    budget.counters["candidate_documents_observed"] += 1
                    if not _is_within(path, repository_path):
                        candidates.append(rel_path)
                        outside_selected.add(rel_path)
                        continue
                    candidates.append(rel_path)
        if stop:
            break

    docs: list[Doc] = []
    rejected: list[dict] = []
    omitted: list[dict] = []
    candidates.sort(key=lambda path: _rank(path, query))
    for rel_path in candidates:
        if rel_path in outside_selected:
            rejected.append(route_item(rel_path, "outside-root", "route.docs.scope"))
            continue
        body = active_reader.read(rel_path)
        if body is not None:
            docs.append(_parse_doc(rel_path, body))
            continue
        reason = active_reader.reason(rel_path) or "unreadable"
        if reason in {"max-docs", "budget-exhausted"}:
            omitted.append(
                route_item(
                    rel_path,
                    reason,
                    f"route.docs.{reason}",
                    boundary=budget.exhausted_at if reason == "budget-exhausted" else None,
                )
            )
        else:
            rejected.append(route_item(rel_path, reason, "route.docs.read"))

    complete = enumeration_complete and not budget.exhausted
    reconciliation = reconcile_route(
        candidates,
        (doc.rel_path for doc in docs),
        rejected,
        omitted,
    )
    reconciliation["enumeration_complete"] = enumeration_complete
    reconciliation["enumeration_boundary"] = enumeration_boundary
    return DocumentResult(
        tuple(docs),
        tuple(candidates),
        tuple(rejected),
        tuple(omitted),
        complete,
        reconciliation,
    )
