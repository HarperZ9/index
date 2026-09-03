"""Git subprocess access and always-on credential redaction."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

# A web remote carries its whole userinfo as a secret. The token often
# sits in the user slot with no password beside it, so the slot goes as a
# unit.
_USERINFO = re.compile(r"(?i)(https?://)[^/@]+@")
# Every other scheme keeps its username, because ssh://git@host names a
# user and nothing more. A colon means a password came with it, and that
# is a secret whatever the scheme says.
_PASSWORD_USERINFO = re.compile(
    r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]*:[^/@\s]*@")
# Parameter names arrive prefixed as often as bare, so access_token has to
# match as readily as token. The value class runs to the end of the query
# on purpose: swallowing a trailing parameter redacts more than was asked
# for, and the alternative is publishing a second secret whose name this
# pattern does not know.
_SECRET_QUERY = re.compile(
    r"(?i)(?<![\w-])([\w-]*(?:token|password|secret|api[_-]?key))=([^@\s]+)")


def sanitize_credentials(origin: str) -> str:
    """Strip the parts of a remote URL a reader of the map must not get.

    What survives is the scheme, the host and the path, which is what
    makes a remote recognisable. Every origin passes through here before
    it reaches a row, so a map cannot carry a credential even when the
    clone URL held one.
    """
    clean = _USERINFO.sub(r"\1<redacted>@", origin)
    clean = _PASSWORD_USERINFO.sub(r"\1<redacted>@", clean)
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
