"""Git subprocess access and always-on credential redaction."""

from __future__ import annotations

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
