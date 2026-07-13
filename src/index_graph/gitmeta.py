"""Git subprocess access and always-on credential redaction."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

_USERINFO = re.compile(r"(?i)(https?://)[^/@]+@")
_SECRET_QUERY = re.compile(r"(?i)\b(token|password|secret|api[_-]?key)=([^@\s]+)")


def sanitize_credentials(origin: str) -> str:
    clean = _USERINFO.sub(r"\1<redacted>@", origin)
    return _SECRET_QUERY.sub(r"\1=<redacted>", clean)


def run_git(repo: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True, capture_output=True, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def canonical_path_identity(path: Path) -> str:
    absolute = os.path.abspath(path)
    try:
        physical = os.path.realpath(absolute)
    except OSError:
        physical = absolute
    return os.path.normcase(physical)


def _recorded_path(raw: str, base: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else base / path


def _gitfile_target(gitfile: Path) -> Path | None:
    try:
        text = gitfile.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    prefix, separator, raw = text.partition(":")
    if separator != ":" or prefix.casefold() != "gitdir" or not raw.strip():
        return None
    return _recorded_path(raw.strip(), gitfile.parent)


def gitfile_backlink_matches(repo: Path) -> bool:
    gitfile = repo / ".git"
    if not gitfile.is_file():
        return True
    admin = _gitfile_target(gitfile)
    if admin is None:
        return True
    backlink = admin / "gitdir"
    commondir = admin / "commondir"
    if not commondir.is_file() or not backlink.is_file():
        return True
    try:
        raw = backlink.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return True
    if not raw:
        return True
    registered_gitfile = _recorded_path(raw, backlink.parent)
    return canonical_path_identity(gitfile) == canonical_path_identity(registered_gitfile)


def repo_metadata(repo: Path) -> dict[str, Any]:
    status = run_git(repo, ["status", "--porcelain=v1"]).splitlines()
    untracked = sum(1 for line in status if line.startswith("??"))
    dirty = sum(1 for line in status if line and not line.startswith("??"))
    branch = (
        run_git(repo, ["branch", "--show-current"])
        or run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
        or "unknown"
    )
    head = run_git(repo, ["rev-parse", "--short=7", "HEAD"]) or "unknown"
    origin = sanitize_credentials(run_git(repo, ["config", "--get", "remote.origin.url"]) or "")
    return {
        "branch": branch,
        "head": head,
        "origin": origin,
        "dirty_count": dirty,
        "untracked_count": untracked,
    }
