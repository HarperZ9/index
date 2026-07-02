"""Shared synthetic single-repo fixtures for the verified-wiki tests."""
from __future__ import annotations

import subprocess
from pathlib import Path


def make_repo(root: Path) -> Path:
    """A tiny Python repo with a real internal import chain and docs."""
    root.mkdir(parents=True, exist_ok=True)
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (pkg / "api.py").write_text("from . import core\n", encoding="utf-8")
    (root / "main.py").write_text("import pkg.api\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo\n\nAuthored prose.\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir()
    (docs / "design.md").write_text("# Design\n\nWhy it is shaped so.\n", encoding="utf-8")
    return root


def git_commit_all(root: Path, message: str = "seed") -> str:
    """Init (if needed), stage everything, commit; return the full HEAD sha."""
    def _git(*args: str) -> str:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    if not (root / ".git").exists():
        _git("init", "-q")
        _git("config", "user.email", "wiki-test@example.invalid")
        _git("config", "user.name", "wiki test")
    _git("add", "-A")
    _git("commit", "-q", "-m", message, "--no-gpg-sign")
    return _git("rev-parse", "HEAD")
