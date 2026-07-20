"""Task scope resolution: explicit paths, map hints, scoring, bounded discovery."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from ..config import load_config
from ..scan import discover_repos
from .budget import WorkBudget
from .model import RouteRequest, reconcile_route, route_item
from .reads import DocumentReader

_TOKEN = re.compile(r"[0-9a-z]+")


@dataclass(frozen=True)
class RepoCandidate:
    id: str
    path: Path | None
    rel_path: str
    source: str
    score: int = 0
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopeResult:
    candidates: tuple[RepoCandidate, ...]
    selected: tuple[RepoCandidate, ...]
    rejected: tuple[dict, ...]
    omitted: tuple[dict, ...]
    complete: bool
    source: dict
    reconciliation: dict


def _root_id(root: Path) -> str:
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]


def _candidate(
    root: Path, path: Path, source: str, metadata: dict | None = None
) -> RepoCandidate:
    rel = path.relative_to(root).as_posix() or "."
    terms = {rel.lower(), path.name.lower()}
    if metadata:
        terms.add(str(metadata.get("class", "")).lower())
        terms.update(str(marker).lower() for marker in metadata.get("markers", ()))
        terms.update(str(term).lower() for term in metadata.get("annotations", ()))
        if metadata.get("readme_title"):
            terms.add(str(metadata["readme_title"]).lower())
    return RepoCandidate(rel, path, rel, source, signals=tuple(sorted(terms)))


def _score(candidate: RepoCandidate, query: str) -> RepoCandidate:
    tokens = set(_TOKEN.findall(query.lower()))
    matched = tuple(
        sorted(
            token
            for token in tokens
            if any(token in signal for signal in candidate.signals)
        )
    )
    return RepoCandidate(
        candidate.id,
        candidate.path,
        candidate.rel_path,
        candidate.source,
        score=len(matched),
        signals=candidate.signals + tuple(f"query:{token}" for token in matched),
    )


def _receipt(candidate: RepoCandidate, reason: str, rule: str, **evidence: object) -> dict:
    return route_item(candidate.id, reason, rule, **evidence)


def _safe_explicit_candidate(root: Path, raw_path: str) -> tuple[RepoCandidate, dict | None]:
    candidate_path = Path(raw_path)
    resolved = candidate_path.resolve() if candidate_path.is_absolute() else (root / candidate_path).resolve()
    try:
        return _candidate(root, resolved, "explicit"), None
    except ValueError:
        digest = hashlib.sha256(raw_path.encode("utf-8")).hexdigest()[:16]
        redacted = RepoCandidate(
            f"outside-root:{digest}", None, f"outside-root:{digest}", "explicit"
        )
        return redacted, _receipt(redacted, "outside-root", "route.explicit.root")


def _map_candidates(
    root: Path, data: dict, annotations: dict
) -> tuple[list[RepoCandidate], list[tuple[RepoCandidate, dict]]]:
    candidates: list[RepoCandidate] = []
    rejected: list[tuple[RepoCandidate, dict]] = []
    for row in data.get("repositories", ()):
        raw_path = str(row.get("path", ""))
        try:
            path = (root / raw_path).resolve()
            candidate = _candidate(
                root,
                path,
                "workspace-map",
                {
                    **row,
                    "annotations": _annotation_values(annotations.get(raw_path)),
                },
            )
        except ValueError:
            digest = hashlib.sha256(raw_path.encode("utf-8")).hexdigest()[:16]
            candidate = RepoCandidate(
                f"outside-root:{digest}", None, f"outside-root:{digest}", "workspace-map"
            )
            rejected.append(
                (candidate, _receipt(candidate, "outside-root", "route.map.root"))
            )
        candidates.append(candidate)
    return candidates, rejected


def _annotation_values(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    return (str(value),)


def _map_data(root: Path) -> tuple[dict | None, Path | None]:
    map_path = root / "WORKSPACE-REPO-MAP.json"
    if not map_path.is_file():
        return None, None
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, map_path
    if data.get("root_sha256_prefix") != _root_id(root):
        return None, map_path
    return data, map_path


def _readme_title(reader: DocumentReader, repository: Path) -> str | None:
    body = reader.read(repository / "README.md")
    if body is None:
        return None
    match = re.search(r"(?m)^\s*#\s+(.+?)\s*$", body)
    return match.group(1) if match else None


def _validated(candidate: RepoCandidate) -> tuple[bool, str | None]:
    assert candidate.path is not None
    try:
        if not candidate.path.exists():
            return False, "not-found"
        if not (candidate.path / ".git").exists():
            return False, "not-repository"
    except OSError:
        return False, "unreadable"
    return True, None


def _source(kind: str, validation: str, map_data: dict | None = None) -> dict:
    source = {"kind": kind, "validation": validation}
    if map_data is not None:
        source["map_path"] = "WORKSPACE-REPO-MAP.json"
        source["map_age"] = map_data.get("generated_at")
    return source


def _dedupe_rejections(
    rejections: list[tuple[RepoCandidate, dict]]
) -> list[tuple[RepoCandidate, dict]]:
    return list({candidate.id: (candidate, receipt) for candidate, receipt in rejections}.values())


def _record_budget_omission(source: dict, rule_ref: str, budget: WorkBudget) -> None:
    source.setdefault("omissions", []).append({
        "reason_code": "budget-exhausted",
        "rule_ref": rule_ref,
        "boundary": budget.exhausted_at,
    })


def _record_map_rejections(source: dict, rejections: list[tuple[RepoCandidate, dict]]) -> None:
    if rejections:
        source["map_rejections"] = [receipt for _, receipt in _dedupe_rejections(rejections)]


def resolve_scope(
    request: RouteRequest, budget: WorkBudget, *, reader: DocumentReader | None = None
) -> ScopeResult:
    """Resolve a portable repository shortlist without exceeding route bounds."""
    config = load_config(None, request.root)
    complete = True
    source: dict
    initial_rejections: list[tuple[RepoCandidate, dict]] = []

    if request.paths:
        candidates_by_id: dict[str, RepoCandidate] = {}
        for raw_path in request.paths:
            candidate, rejection = _safe_explicit_candidate(request.root, raw_path)
            if candidate.path is not None:
                candidate = _candidate(
                    request.root,
                    candidate.path,
                    "explicit",
                    {
                        "annotations": _annotation_values(
                            config.annotations.get(candidate.id)
                        ),
                    },
                )
            candidates_by_id[candidate.id] = candidate
            if rejection is not None:
                initial_rejections.append((candidate, rejection))
        candidates = [candidates_by_id[candidate_id] for candidate_id in sorted(candidates_by_id)]
        source = _source("explicit", "DIRECT")
    else:
        map_data, map_path = _map_data(request.root)
        if map_data is not None:
            candidates, initial_rejections = _map_candidates(
                request.root,
                map_data,
                {**map_data.get("annotations", {}), **config.annotations},
            )
            candidates = sorted({candidate.id: candidate for candidate in candidates}.values(), key=lambda item: item.id)
            source = _source("workspace-map", "UNVERIFIED", map_data)
            _record_map_rejections(source, initial_rejections)
            complete = False
            if request.freshness == "strict":
                discovered = discover_repos(
                    request.root,
                    config,
                    checkpoint=budget.callback("directories_visited"),
                    prune_repo_contents=True,
                )
                if budget.exhausted:
                    source = _source("workspace-map", "UNKNOWN", map_data)
                    _record_map_rejections(source, initial_rejections)
                    _record_budget_omission(source, "route.strict.discovery", budget)
                else:
                    discovered_candidates = [
                        _candidate(request.root, path, "discovery", {
                            "annotations": _annotation_values(config.annotations.get(path.relative_to(request.root).as_posix() or ".")),
                        })
                        for path in discovered
                    ]
                    map_ids = {candidate.id for candidate in candidates if candidate.path is not None}
                    discovered_ids = {candidate.id for candidate in discovered_candidates}
                    complete = True
                    if map_ids == discovered_ids and not initial_rejections:
                        source = _source("workspace-map", "FRESH", map_data)
                    else:
                        candidates = discovered_candidates
                        source = _source("workspace-map", "DRIFT", map_data)
                        _record_map_rejections(source, initial_rejections)
                        initial_rejections = []
        else:
            discovered = discover_repos(
                request.root,
                config,
                checkpoint=budget.callback("directories_visited"),
                prune_repo_contents=True,
            )
            candidates = [
                _candidate(request.root, path, "discovery", {
                    "annotations": _annotation_values(config.annotations.get(path.relative_to(request.root).as_posix() or ".")),
                })
                for path in discovered
            ]
            if budget.exhausted:
                complete = False
            source = _source("discovery", "FRESH" if complete else "UNKNOWN")
            if budget.exhausted:
                _record_budget_omission(source, "route.discovery", budget)

    candidates = [_score(candidate, request.query) for candidate in candidates]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.id))
    initial_rejections = _dedupe_rejections(initial_rejections)
    rejected = [item for _, item in initial_rejections]
    rejected_ids = {candidate.id for candidate, _ in initial_rejections}
    omitted: list[dict] = []
    shortlisted: list[RepoCandidate] = []
    for candidate in candidates:
        if candidate.id in rejected_ids:
            continue
        if len(shortlisted) < request.max_repos:
            shortlisted.append(candidate)
        else:
            omitted.append(_receipt(candidate, "max-repos", f"route.max_repos:{request.max_repos}"))

    result_candidates = {candidate.id: candidate for candidate in candidates}
    selected: list[RepoCandidate] = []
    active_reader = reader or DocumentReader(request.root, request.max_docs, budget)
    for index, candidate in enumerate(shortlisted):
        if not budget.checkpoint("scope.repo", counter="repositories_visited"):
            complete = False
            for remaining in shortlisted[index:]:
                omitted.append(
                    _receipt(
                        remaining,
                        "budget-exhausted",
                        "route.scope.repo",
                        boundary=budget.exhausted_at,
                    )
                )
            break
        if candidate.path is None:
            continue
        valid, reason = _validated(candidate)
        if not valid:
            rejected_candidate = replace(candidate, path=None)
            result_candidates[candidate.id] = rejected_candidate
            rejected.append(_receipt(rejected_candidate, reason or "unreadable", "route.scope.validate"))
            continue
        enriched = candidate
        if request.query:
            metadata = {
                "annotations": _annotation_values(config.annotations.get(candidate.id)),
                "readme_title": _readme_title(active_reader, candidate.path),
            }
            if budget.exhausted:
                complete = False
                _record_budget_omission(source, "route.query.readme", budget)
            additions = _candidate(
                request.root, candidate.path, candidate.source, metadata
            )
            enriched = RepoCandidate(
                candidate.id,
                candidate.path,
                candidate.rel_path,
                candidate.source,
                signals=tuple(
                    sorted(
                        set(signal for signal in candidate.signals if not signal.startswith("query:"))
                        | set(additions.signals)
                    )
                ),
            )
            enriched = _score(enriched, request.query)
        result_candidates[candidate.id] = enriched
        selected.append(enriched)

    selected.sort(key=lambda candidate: (-candidate.score, candidate.id))
    result_list = tuple(result_candidates[candidate.id] for candidate in candidates)
    reconciliation = reconcile_route(
        (candidate.id for candidate in result_list),
        (candidate.id for candidate in selected),
        rejected,
        omitted,
    )
    return ScopeResult(
        result_list,
        tuple(selected),
        tuple(rejected),
        tuple(omitted),
        complete,
        source,
        reconciliation,
    )
