"""Git subprocess access and always-on credential redaction."""

from __future__ import annotations

from dataclasses import dataclass
import re
import os
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_GIT_TIMEOUT_SECONDS = 5.0
STATUS_GLOBAL_ARGS = ["--no-optional-locks"]
STATUS_ARGS = ["status", "--porcelain=v2", "--branch", "--untracked-files=all"]


@dataclass(frozen=True)
class GitCommandResult:
    ok: bool
    stdout: str
    error: str | None = None


class GitMetadataError(RuntimeError):
    """Raised when repo cleanliness cannot be established safely."""


def git_timeout_seconds() -> float:
    raw = os.environ.get("INDEX_GIT_TIMEOUT_SECONDS")
    if raw is None or raw == "":
        return DEFAULT_GIT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_GIT_TIMEOUT_SECONDS
    return max(0.1, value)


def _git_env(repo: Path) -> dict[str, str]:
    env = dict(os.environ)
    ceiling = str(Path(repo).resolve().parent)
    existing = env.get("GIT_CEILING_DIRECTORIES")
    if existing:
        parts = [part for part in existing.split(os.pathsep) if part]
        if ceiling not in parts:
            parts.append(ceiling)
        env["GIT_CEILING_DIRECTORIES"] = os.pathsep.join(parts)
    else:
        env["GIT_CEILING_DIRECTORIES"] = ceiling
    return env

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


def run_git_checked(
    repo: Path,
    args: list[str],
    *,
    global_args: list[str] | None = None,
) -> GitCommandResult:
    try:
        result = subprocess.run(
            ["git", *(global_args or []), "-C", str(repo), *args],
            text=True, capture_output=True, timeout=git_timeout_seconds(), check=False,
            env=_git_env(repo),
        )
    except subprocess.TimeoutExpired:
        return GitCommandResult(False, "", "timeout")
    if result.returncode != 0:
        return GitCommandResult(False, "", f"exit-{result.returncode}")
    return GitCommandResult(True, result.stdout.strip())


def run_git(repo: Path, args: list[str]) -> str:
    result = run_git_checked(repo, args)
    return result.stdout if result.ok else ""


def _branch_from_status(lines: list[str]) -> str:
    if not lines or not lines[0].startswith("## "):
        return ""
    branch = lines[0][3:].strip()
    if branch.startswith("No commits yet on "):
        return branch.removeprefix("No commits yet on ").strip() or ""
    if "..." in branch:
        branch = branch.split("...", 1)[0]
    if branch.endswith("]") and "[" in branch:
        branch = branch.rsplit("[", 1)[0].strip()
    return branch or ""


def _metadata_from_porcelain_v2(status: str) -> tuple[str, str, int, int]:
    branch = ""
    head = ""
    dirty = 0
    untracked = 0
    for line in status.splitlines():
        if line.startswith("# branch.head "):
            branch = line.removeprefix("# branch.head ").strip()
            if branch == "(detached)":
                branch = "HEAD"
        elif line.startswith("# branch.oid "):
            oid = line.removeprefix("# branch.oid ").strip()
            if oid and oid != "(initial)":
                head = oid[:7]
        elif line.startswith("? "):
            untracked += 1
        elif line and not line.startswith("# "):
            dirty += 1
    return branch, head, dirty, untracked


def _status_signature(status: str) -> str:
    import hashlib

    return hashlib.sha256(status.encode("utf-8")).hexdigest()


def repo_metadata(repo: Path) -> dict[str, Any]:
    status_result = run_git_checked(repo, STATUS_ARGS, global_args=STATUS_GLOBAL_ARGS)
    if not status_result.ok:
        raise GitMetadataError(f"git status unavailable: {status_result.error or 'unknown'}")
    branch, head, dirty, untracked = _metadata_from_porcelain_v2(status_result.stdout)
    status_lines = status_result.stdout.splitlines()
    branch = (
        branch
        or _branch_from_status(status_lines)
        or run_git(repo, ["branch", "--show-current"])
        or run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
        or "unknown"
    )
    head = head or run_git(repo, ["rev-parse", "--short=7", "HEAD"]) or "unknown"
    origin = sanitize_credentials(run_git(repo, ["config", "--get", "remote.origin.url"]) or "")
    return {
        "branch": branch,
        "head": head,
        "origin": origin,
        "dirty_count": dirty,
        "untracked_count": untracked,
        "metadata_status": "ok",
        "metadata_error": None,
        "status_signature": _status_signature(status_result.stdout),
    }
