"""Discovery, parallel git fan-out, and map assembly."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from .classify import classify
from .config import Config
from .gitmeta import STATUS_ARGS, STATUS_GLOBAL_ARGS, GitMetadataError, repo_metadata, run_git_checked
from .model import SCHEMA_VERSION, Map, RepoRow


DEFAULT_INTERACTIVE_BUDGET_MS = 12000
DEFAULT_INTERACTIVE_REPO_LIMIT = 300
_MAP_RESUME_ROW_SCHEMA = "index.map-resume-row/v2"


class ScanBudget:
    """Cooperative wall-clock budget for workspace traversal."""

    def __init__(self, budget_ms: int | None):
        self.budget_ms = int(budget_ms or 0)
        self.started = perf_counter()
        self.deadline = self.started + (self.budget_ms / 1000.0) if self.budget_ms > 0 else None
        self.exhausted = False
        self.last_path: Path | None = None

    def checkpoint(self, path: Path) -> bool:
        self.last_path = Path(path)
        if self.deadline is None:
            return True
        if perf_counter() <= self.deadline:
            return True
        self.exhausted = True
        return False

    @property
    def elapsed_ms(self) -> int:
        return int((perf_counter() - self.started) * 1000)


class ScanBudgetExceeded(RuntimeError):
    """Raised by caller wrappers when a partial discovery must not be authoritative."""

    def __init__(self, *, root: Path, budget: ScanBudget, repo_count: int, skipped: list | None = None):
        self.root = Path(root)
        self.budget_ms = budget.budget_ms
        self.elapsed_ms = budget.elapsed_ms
        self.repo_count = repo_count
        self.skipped = list(skipped or [])
        self.last_path = str(budget.last_path) if budget.last_path is not None else None
        super().__init__(
            f"repository discovery budget exhausted after {self.elapsed_ms} ms "
            f"(budget_ms={self.budget_ms}, partial_repos={repo_count})"
        )


class ScanWorkloadExceeded(RuntimeError):
    """Raised when complete discovery is too large for an interactive graph build."""

    def __init__(self, *, repo_count: int, repo_limit: int, budget_ms: int):
        self.repo_count = repo_count
        self.repo_limit = repo_limit
        self.budget_ms = budget_ms
        super().__init__(
            f"workspace has {repo_count} repositories, exceeding the interactive graph limit "
            f"of {repo_limit} while budget_ms={budget_ms}"
        )


def default_interactive_budget_ms() -> int:
    raw = os.environ.get("INDEX_INTERACTIVE_BUDGET_MS")
    if raw is None or raw == "":
        return DEFAULT_INTERACTIVE_BUDGET_MS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_INTERACTIVE_BUDGET_MS
    return max(0, value)


def default_interactive_repo_limit() -> int:
    raw = os.environ.get("INDEX_INTERACTIVE_REPO_LIMIT")
    if raw is None or raw == "":
        return DEFAULT_INTERACTIVE_REPO_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_INTERACTIVE_REPO_LIMIT
    return max(0, value)


def enforce_interactive_repo_limit(repo_count: int, *, budget_ms: int | None) -> None:
    if not budget_ms:
        return
    limit = default_interactive_repo_limit()
    if limit and repo_count > limit:
        raise ScanWorkloadExceeded(repo_count=repo_count, repo_limit=limit, budget_ms=int(budget_ms))


def _root_hash(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _warn(message: str) -> None:
    try:
        print(message, file=sys.stderr)
    except UnicodeError:
        safe = message.encode("utf-8", "backslashreplace").decode("ascii", "replace")
        print(safe, file=sys.stderr)


def discover_repos(root: Path, config: Config, *,
                   skipped: list | None = None,
                   checkpoint: Callable[[Path], bool] | None = None) -> list[Path]:
    root = Path(root)
    prune = config.prune
    repos: set[Path] = set()
    def _onerror(exc: OSError) -> None:
        # a directory os.walk could not read narrows the scan: record it so a
        # partial scan is a receiptable fact, not a stderr-only warning that a
        # certificate can MATCH straight past
        if skipped is not None:
            skipped.append(getattr(exc, "filename", None) or str(exc))
        _warn(f"warning: skipped unreadable directory during repo discovery: {exc}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=_onerror):
        current = Path(dirpath)
        if checkpoint is not None and not checkpoint(current):
            if skipped is not None:
                skipped.append(f"scan-budget-exhausted:{current}")
            _warn(f"warning: repository discovery budget exhausted at {current}")
            dirnames[:] = []
            break
        is_repo = ".git" in dirnames or ".git" in filenames
        if is_repo:
            repos.add(current)
            if current != root and not config.descend_into_repos:
                dirnames[:] = []
                continue
        dirnames[:] = sorted((name for name in dirnames if name not in prune), key=str.lower)
    return sorted(repos, key=lambda p: p.relative_to(root).as_posix().lower())


def repo_key_map(
    root: Path,
    repos: list[Path],
    *,
    include_root_repo: bool = False,
) -> dict[str, Path]:
    """Map discovered repos to stable keys without dropping duplicate basenames.

    Unique basenames keep the short legacy key. When multiple repos share a
    basename, each duplicate gets its relative workspace path as the key.
    """
    root = Path(root)
    filtered = [
        repo for repo in repos
        if include_root_repo or repo != root or len(repos) == 1
    ]
    counts = Counter(repo.name for repo in filtered)
    keyed: dict[str, Path] = {}
    for repo in filtered:
        if counts[repo.name] == 1:
            key = repo.name
        else:
            key = repo.relative_to(root).as_posix()
        keyed[key] = repo
    return keyed


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return path.name


@dataclass(frozen=True)
class _ResumeEntry:
    row: RepoRow
    identity: dict[str, Any]


def _repo_row_from_meta(repo: Path, root: Path, config: Config, meta: dict[str, Any]) -> RepoRow:
    rel = _relative(repo, root)
    class_ = classify(rel, True, meta["origin"], config)
    origin = "" if class_ in config.omit_origin_classes else meta["origin"]
    path = rel if config.portable else str(repo)
    markers = tuple(name for name in config.markers if (repo / name).exists())
    return RepoRow(
        path=path, class_=class_, branch=meta["branch"], head=meta["head"],
        origin=origin, dirty_count=meta["dirty_count"],
        untracked_count=meta["untracked_count"], markers=markers,
        metadata_status=str(meta.get("metadata_status") or "ok"),
        metadata_error=meta.get("metadata_error"),
    )


def _repo_row(repo: Path, root: Path, config: Config) -> RepoRow:
    return _repo_row_from_meta(repo, root, config, repo_metadata(repo))


def _repo_row_from_json(data: dict[str, Any]) -> RepoRow | None:
    try:
        return RepoRow(
            path=str(data["path"]),
            class_=str(data["class"]),
            branch=str(data["branch"]),
            head=str(data["head"]),
            origin=str(data.get("origin", "")),
            dirty_count=int(data.get("dirty_count", 0)),
            untracked_count=int(data.get("untracked_count", 0)),
            markers=tuple(str(item) for item in data.get("markers", [])),
            metadata_status=str(data.get("metadata_status") or "ok"),
            metadata_error=(
                str(data["metadata_error"])
                if data.get("metadata_error") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


def repo_status_signature(repo: Path) -> str | None:
    result = run_git_checked(repo, STATUS_ARGS, global_args=STATUS_GLOBAL_ARGS)
    if not result.ok:
        return None
    return _sha256_text(result.stdout)


def _config_resume_identity(config: Config) -> str:
    payload = {
        "rules": [(rule.pattern, rule.class_) for rule in config.rules],
        "prune": sorted(config.prune),
        "markers": list(config.markers),
        "descend_into_repos": config.descend_into_repos,
        "include_root_repo": config.include_root_repo,
        "omit_origin_classes": sorted(config.omit_origin_classes),
        "portable": config.portable,
    }
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def _file_identity(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"state": "missing"}
    except OSError as exc:
        return {"state": "unreadable", "error": type(exc).__name__}
    if path.is_dir():
        return {"state": "directory"}
    try:
        digest = _sha256_bytes(path.read_bytes())
    except FileNotFoundError:
        return {"state": "missing"}
    except OSError as exc:
        return {
            "state": "unreadable",
            "error": type(exc).__name__,
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
    return {
        "state": "file",
        "size": stat.st_size,
        "sha256": digest,
    }


def _git_dir(repo: Path) -> Path | None:
    marker = repo / ".git"
    try:
        if marker.is_dir():
            return marker.resolve()
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    prefix = "gitdir:"
    if not text.lower().startswith(prefix):
        return None
    raw = text[len(prefix):].strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = marker.parent / path
    try:
        return path.resolve()
    except OSError:
        return None


def _common_git_dir(git_dir: Path) -> Path:
    common = git_dir / "commondir"
    try:
        raw = common.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return git_dir
    if not raw:
        return git_dir
    path = Path(raw)
    if not path.is_absolute():
        path = git_dir / path
    try:
        return path.resolve()
    except OSError:
        return git_dir


def _git_control_identity(repo: Path) -> str:
    marker = repo / ".git"
    parts: list[tuple[str, dict[str, Any]]] = [(".git", _file_identity(marker))]
    git_dir = _git_dir(repo)
    if git_dir is None:
        return _sha256_text(json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str))
    common_dir = _common_git_dir(git_dir)
    for base_name, base in (("gitdir", git_dir), ("commondir", common_dir)):
        for name in ("HEAD", "config", "index", "packed-refs", "commondir"):
            parts.append((f"{base_name}/{name}", _file_identity(base / name)))
    try:
        head_text = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        head_text = ""
    if head_text.startswith("ref:"):
        ref = head_text.split(":", 1)[1].strip()
        if ref:
            for base_name, base in (("gitdir", git_dir), ("commondir", common_dir)):
                parts.append((f"{base_name}/{ref}", _file_identity(base / ref)))
    return _sha256_text(json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str))


def _repo_resume_identity(
    repo: Path,
    root: Path,
    config: Config,
    *,
    status_signature: str | None = None,
) -> dict[str, Any] | None:
    signature = status_signature or repo_status_signature(repo)
    if signature is None:
        return None
    marker_state = []
    for name in config.markers:
        path = repo / name
        try:
            exists = path.exists()
        except OSError:
            exists = False
        marker_state.append([name, exists])
    return {
        "repo_relative": _relative(repo, root),
        "config": _config_resume_identity(config),
        "markers": marker_state,
        "git_status": signature,
        "git_control": _git_control_identity(repo),
    }


def _load_resume_rows(resume_state: Path | None, root: Path) -> dict[str, _ResumeEntry]:
    if resume_state is None:
        return {}
    rows: dict[str, _ResumeEntry] = {}
    root_id = _root_hash(root)
    try:
        lines = resume_state.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("schema") != _MAP_RESUME_ROW_SCHEMA:
            continue
        if rec.get("root_sha256_prefix") != root_id:
            continue
        rel = rec.get("repo_relative")
        row = _repo_row_from_json(rec.get("row") or {})
        identity = rec.get("identity")
        if isinstance(rel, str) and row is not None and isinstance(identity, dict):
            rows[rel] = _ResumeEntry(row, identity)
    return rows


def _append_resume_row(
    resume_state: Path | None,
    root: Path,
    repo: Path,
    row: RepoRow,
    identity: dict[str, Any] | None,
) -> None:
    if resume_state is None or identity is None:
        return
    rec = {
        "schema": _MAP_RESUME_ROW_SCHEMA,
        "root_sha256_prefix": _root_hash(root),
        "repo_relative": _relative(repo, root),
        "identity": identity,
        "row": row.to_json(),
    }
    try:
        resume_state.parent.mkdir(parents=True, exist_ok=True)
        with resume_state.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError as exc:
        _warn(f"warning: could not write map resume state {resume_state}: {exc}")


def _unknown_repo_row(repo: Path, root: Path, config: Config, exc: Exception) -> RepoRow:
    rel = _relative(repo, root)
    _warn(f"warning: failed to scan {rel}: {exc}")
    class_ = classify(rel, True, "", config) if isinstance(exc, GitMetadataError) else "unknown"
    return RepoRow(
        path=(rel if config.portable else str(repo)), class_=class_,
        branch="unknown", head="unknown", origin="", dirty_count=0,
        untracked_count=0, markers=(), metadata_status="unknown",
        metadata_error=type(exc).__name__,
    )


def _safe_repo_row(repo: Path, root: Path, config: Config) -> RepoRow:
    # Spec §9: one repo's failure must degrade to a row, never crash the scan.
    try:
        return _repo_row(repo, root, config)
    except Exception as exc:
        return _unknown_repo_row(repo, root, config, exc)


def _safe_resume_entry(repo: Path, root: Path, config: Config) -> tuple[RepoRow, dict[str, Any] | None]:
    try:
        meta = repo_metadata(repo)
        row = _repo_row_from_meta(repo, root, config, meta)
        identity = _repo_resume_identity(
            repo,
            root,
            config,
            status_signature=meta.get("status_signature"),
        )
        if row.metadata_status != "ok":
            identity = None
        return row, identity
    except Exception as exc:
        return _unknown_repo_row(repo, root, config, exc), None


def _cached_resume_identity(repo: Path, root: Path, config: Config) -> dict[str, Any] | None:
    try:
        return _repo_resume_identity(repo, root, config)
    except Exception:
        return None


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


def _map_rows(root: Path, config: Config, repos: list[Path], resume_state: Path | None) -> list[RepoRow]:
    cached = _load_resume_rows(resume_state, root)
    rows_by_rel: dict[str, RepoRow] = {}
    pending: list[Path] = []
    if resume_state is None:
        with ThreadPoolExecutor(max_workers=config.jobs) as pool:
            futures = {pool.submit(_safe_repo_row, repo, root, config): repo for repo in repos}
            for future in as_completed(futures):
                repo = futures[future]
                rows_by_rel[_relative(repo, root)] = future.result()
        return [rows_by_rel[_relative(repo, root)] for repo in repos]

    cached_candidates: list[Path] = []
    for repo in repos:
        if _relative(repo, root) in cached:
            cached_candidates.append(repo)
        else:
            pending.append(repo)
    if cached_candidates:
        with ThreadPoolExecutor(max_workers=config.jobs) as pool:
            futures = {pool.submit(_cached_resume_identity, repo, root, config): repo for repo in cached_candidates}
            for future in as_completed(futures):
                repo = futures[future]
                rel = _relative(repo, root)
                entry = cached[rel]
                current_identity = future.result()
                if current_identity is not None and entry.identity == current_identity:
                    rows_by_rel[rel] = entry.row
                else:
                    pending.append(repo)
    if pending:
        with ThreadPoolExecutor(max_workers=config.jobs) as pool:
            futures = {pool.submit(_safe_resume_entry, repo, root, config): repo for repo in pending}
            for future in as_completed(futures):
                repo = futures[future]
                row, identity = future.result()
                rel = _relative(repo, root)
                rows_by_rel[rel] = row
                _append_resume_row(resume_state, root, repo, row, identity)
    return [rows_by_rel[_relative(repo, root)] for repo in repos]


def build_map(
    root: Path,
    config: Config,
    tool_version: str,
    *,
    resume_state: Path | None = None,
) -> Map:
    root = root.resolve()
    resume_state = resume_state.resolve() if resume_state is not None else None
    repo_paths = discover_repos(root, config)
    rows = _map_rows(root, config, repo_paths, resume_state)
    class_counts: dict[str, int] = {}
    for row in rows:
        class_counts[row.class_] = class_counts.get(row.class_, 0) + 1
    return Map(
        schema_version=SCHEMA_VERSION,
        tool_version=tool_version,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        root_sha256_prefix=_root_hash(root),
        root=None if config.portable else str(root),
        absolute_paths_included=not config.portable,
        repo_count=len(rows),
        dirty_count=sum(row.dirty_count for row in rows if row.metadata_status == "ok"),
        class_counts=class_counts,
        top_level=tuple(_top_level(root, config)),
        repositories=tuple(rows),
        annotations=dict(config.annotations),
    )


def write_map(
    root: Path,
    config: Config,
    tool_version: str,
    output: Path,
    *,
    resume_state: Path | None = None,
) -> Map:
    data = build_map(root, config, tool_version, resume_state=resume_state)
    output.write_text(json.dumps(data.to_json(), indent=2) + "\n", encoding="utf-8")
    return data
