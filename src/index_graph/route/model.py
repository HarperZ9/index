"""Validated route requests and closed-world route receipts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, Sequence


ROUTE_SCHEMA = "index.route-receipt/v1"
DEFAULT_MAX_REPOS = 12
DEFAULT_MAX_DOCS = 8
DEFAULT_BUDGET_MS = 5000
FRESHNESS_MODES = frozenset({"bounded", "strict"})
VERDICTS = frozenset({"MATCH", "PARTIAL", "STALE", "UNVERIFIABLE"})
REASON_CODES = frozenset(
    {
        "outside-root",
        "not-found",
        "not-repository",
        "unreadable",
        "duplicate",
        "max-repos",
        "max-docs",
        "budget-exhausted",
        "stale-manifest",
    }
)


@dataclass(frozen=True)
class RouteRequest:
    """Normalized, validated controls for one bounded route request."""

    root: Path
    query: str
    paths: tuple[str, ...]
    max_repos: int
    max_docs: int
    budget_ms: int
    freshness: str

    @classmethod
    def create(
        cls,
        root: Path | str,
        *,
        query: str = "",
        paths: Sequence[str] = (),
        max_repos: int = DEFAULT_MAX_REPOS,
        max_docs: int = DEFAULT_MAX_DOCS,
        budget_ms: int = DEFAULT_BUDGET_MS,
        freshness: str = "bounded",
    ) -> "RouteRequest":
        """Resolve and validate route controls before any filesystem work."""
        if max_repos < 0:
            raise ValueError("max_repos must be >= 0")
        if max_docs < 0:
            raise ValueError("max_docs must be >= 0")
        if budget_ms < 1:
            raise ValueError("budget_ms must be >= 1")
        if freshness not in FRESHNESS_MODES:
            raise ValueError("freshness must be bounded or strict")
        resolved_root = Path(root).resolve()
        normalized_paths = []
        for path in paths:
            raw_path = str(path)
            windows_path = PureWindowsPath(raw_path)
            candidate = Path(raw_path.replace("\\", "/"))
            host_rooted_windows_path = bool(
                getattr(resolved_root, "drive", "")
            ) and bool(windows_path.root)
            looks_absolute_or_drive_rooted = (
                windows_path.is_absolute()
                or bool(windows_path.drive)
                or PurePosixPath(raw_path).is_absolute()
            )
            if looks_absolute_or_drive_rooted and not (
                candidate.is_absolute() or host_rooted_windows_path
            ):
                raise ValueError(f"outside-root path: {path}")
            resolved_path = (
                candidate.resolve()
                if candidate.is_absolute()
                else (resolved_root / candidate).resolve()
            )
            try:
                normalized_paths.append(resolved_path.relative_to(resolved_root).as_posix())
            except ValueError as error:
                raise ValueError(f"outside-root path: {path}") from error
        normalized = tuple(dict.fromkeys(normalized_paths))
        return cls(
            resolved_root,
            query.strip(),
            normalized,
            max_repos,
            max_docs,
            budget_ms,
            freshness,
        )


def route_item(path: str, reason_code: str, rule_ref: str, **evidence: object) -> dict:
    """Build a receipt item using only the stable route reason vocabulary."""
    if not isinstance(path, str):
        raise ValueError("path must be a normalized root-relative POSIX path")
    posix_path = PurePosixPath(path)
    windows_path = PureWindowsPath(path)
    if (
        "\\" in path
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or any(part == ".." for part in posix_path.parts)
        or posix_path.as_posix() != path
    ):
        raise ValueError("path must be a normalized root-relative POSIX path")
    if reason_code not in REASON_CODES:
        raise ValueError(f"unknown route reason_code: {reason_code}")
    return {
        "path": path,
        "reason_code": reason_code,
        "rule_ref": rule_ref,
        "evidence": evidence,
    }


def reconcile_route(
    candidates: Iterable[str],
    selected: Iterable[str],
    rejected: Iterable[dict],
    omitted: Iterable[dict],
) -> dict:
    """Confirm every candidate is booked once in the closed-world receipt."""
    candidate_list = list(candidates)
    selected_list = list(selected)
    rejected_list = list(rejected)
    omitted_list = list(omitted)
    booked = selected_list + [item["path"] for item in rejected_list + omitted_list]
    failures = []
    if sorted(candidate_list) != sorted(booked):
        failures.append(
            {
                "code": "candidate-accounting",
                "detail": "candidates must equal selected + rejected + omitted",
            }
        )
    if len(booked) != len(set(booked)):
        failures.append(
            {"code": "duplicate-booking", "detail": "a path was booked twice"}
        )
    return {
        "verdict": "MATCH" if not failures else "DRIFT",
        "counts": {
            "candidates": len(candidate_list),
            "selected": len(selected_list),
            "rejected": len(rejected_list),
            "omitted": len(omitted_list),
        },
        "failures": failures,
    }
