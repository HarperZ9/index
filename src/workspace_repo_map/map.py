"""Refresh the C:\\dev workspace repository map.

The scanner reads Git metadata only. It does not inspect repository contents
beyond checking for a small set of root marker filenames.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

OPERATING_MODEL = (
    "neutral local state-transform boundary; file-backed headless bootstrap; "
    "state/public/protected/research/docs/runtime lanes; provider/API/model/"
    "policy changes are external boundary descriptors, probes, adapter "
    "metadata, and semantic surface contracts"
)
MARKER_FILES = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "CMakeLists.txt",
    "Makefile",
    "requirements.txt",
)
PRUNE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
}
ROOT_CLASSES = {
    ".claude": "local-runtime",
    ".ruff_cache": "generated-or-cache",
    ".warden": "local-runtime",
    ".warden-safe-cache": "generated-or-cache",
    "data": "local-private",
    "frontier-models-research": "research-capture",
    "project-docs": "workspace-docs",
    "protected": "local-only-protected",
    "public": "public",
    "scratch": "generated-or-cache",
    "secrets": "local-private",
    "state": "state",
}
ROOT_BOOTSTRAP_FILES = {
    "AGENTS.md",
    "README.md",
    "SESSION-BOOTSTRAP.md",
    "WORKSPACE-INDEX.md",
    "WORKSPACE-REPO-MAP.json",
    "WORKSPACE-ROADMAP.md",
}
REMOTE_USERINFO_PATTERN = re.compile(r"(?i)(https?://)[^/@]+@")
REMOTE_SECRET_QUERY_PATTERN = re.compile(
    r"(?i)\b(token|password|secret|api[_-]?key)=([^@\s]+)"
)


@dataclass(frozen=True)
class RepoRow:
    path: str
    relative: str
    class_: str
    branch: str
    head: str
    origin: str
    dirty_count: int
    untracked_count: int
    markers: list[str]

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["class"] = data.pop("class_")
        return data


def run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return path.name


def sanitize_origin(origin: str, class_: str) -> str:
    if class_ == "protected" and origin:
        return "<protected-origin-omitted>"
    clean = REMOTE_USERINFO_PATTERN.sub(r"\1<redacted>@", origin)
    return REMOTE_SECRET_QUERY_PATTERN.sub(r"\1=<redacted>", clean)


def discover_repos(root: Path) -> list[Path]:
    repos: set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if ".git" in dirnames or ".git" in filenames:
            repos.add(current)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in PRUNE_DIRS and not _skip_generated_tree(current / name, root)
        ]
    return sorted(repos, key=lambda path: path.relative_to(root).as_posix().lower())


def build_map(root: Path) -> dict[str, Any]:
    root = root.resolve()
    repos = [repo_row(path, root) for path in discover_repos(root)]
    normal_rows = [row for row in repos if row.class_ != "protected"]
    protected_rows = [row for row in repos if row.class_ == "protected"]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "root": "<local-root>",
        "root_sha256_prefix": stable_id(str(root)),
        "absolute_paths_included": False,
        "operating_model": OPERATING_MODEL,
        "top_level": top_level_entries(root),
        "repo_count": len(repos),
        "normal_repo_count": len(normal_rows),
        "protected_repo_count": len(protected_rows),
        "normal_dirty_count": sum(row.dirty_count for row in normal_rows),
        "protected_dirty_count": sum(row.dirty_count for row in protected_rows),
        "protected_policy": {
            "path": "protected",
            "redistribution": "do-not-redistribute",
            "raw_session_transcripts_copied": False,
            "manifest": (
                "protected/manifests/"
                "PROTECTED-MIGRATION-MANIFEST-2026-06-10.json"
            ),
        },
        "repositories": [row.to_json() for row in repos],
    }


def repo_row(repo: Path, root: Path) -> RepoRow:
    status_lines = run_git(repo, ["status", "--porcelain=v1"]).splitlines()
    untracked = sum(1 for line in status_lines if line.startswith("??"))
    dirty = sum(1 for line in status_lines if line and not line.startswith("??"))
    branch = run_git(repo, ["branch", "--show-current"])
    if not branch:
        branch = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    class_ = repo_class(repo, root)
    origin = run_git(repo, ["config", "--get", "remote.origin.url"]) or ""
    rel = relative_path(repo, root)
    return RepoRow(
        path=rel,
        relative=rel,
        class_=class_,
        branch=branch,
        head=run_git(repo, ["rev-parse", "--short=7", "HEAD"]) or "unknown",
        origin=sanitize_origin(origin, class_),
        dirty_count=dirty,
        untracked_count=untracked,
        markers=[name for name in MARKER_FILES if (repo / name).exists()],
    )


def repo_class(repo: Path, root: Path) -> str:
    first = repo.relative_to(root).parts[0] if repo != root else ""
    if first == "protected":
        return "protected"
    if first == "public":
        return "public"
    if first == "state":
        return "state"
    return "workspace"


def top_level_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if path.name == ".git":
            continue
        stat = path.stat()
        entries.append(
            {
                "name": path.name,
                "kind": "directory" if path.is_dir() else "file",
                "class": root_class(path),
                "bytes": None if path.is_dir() else stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return entries


def root_class(path: Path) -> str:
    if path.name in ROOT_BOOTSTRAP_FILES:
        return "root-bootstrap"
    if path.name in ROOT_CLASSES:
        return ROOT_CLASSES[path.name]
    if path.name.startswith("."):
        return "local-runtime"
    return "workspace"


def write_map(root: Path, output: Path) -> dict[str, Any]:
    data = build_map(root)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Workspace root. Defaults to C:\\dev when run from the checked-in tool.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to <root>/WORKSPACE-REPO-MAP.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print generated JSON to stdout.")
    return parser


def _skip_generated_tree(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    parts = rel.parts
    return len(parts) >= 2 and parts[0] == "scratch" and parts[1] == "venvs"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    output = args.output.resolve() if args.output else root / "WORKSPACE-REPO-MAP.json"
    data = build_map(root) if args.json else write_map(root, output)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"wrote {output}")
        print(
            f"repos={data['repo_count']} normal_dirty={data['normal_dirty_count']} "
            f"protected_dirty={data['protected_dirty_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
