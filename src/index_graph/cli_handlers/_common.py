"""Shared helpers for the CLI subcommand handlers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..config import load_config
from ..scan import discover_repos


def repo_paths(root: Path) -> dict[str, Path]:
    # discover_repos requires a Config; use neutral defaults for graph/context.
    config = load_config(None, root)
    return {p.name: p for p in discover_repos(root, config)}


def require_dir(root: Path) -> Path:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise SystemExit(f"root not found: {resolved}")
    return resolved


def rel_to_root(root: Path, p: Path) -> str:
    r = p.resolve().relative_to(root).as_posix()
    return "" if r == "." else r  # a repo AT the root -> "" dir


def head_commit(root) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def emit_cert(cert: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(cert, indent=2, sort_keys=True))
    else:
        print(f"verdict={cert['verdict']} findings={len(cert['findings'])}")
        for f in cert["findings"]:
            loc = f" ({f['evidence']})" if f.get("evidence") else ""
            print(f"  [{f['rule']}] {f['detail']}{loc}")
        cov = cert.get("coverage")
        if cov is not None and not cov.get("complete", True):
            n = len(cov.get("unverifiable_repos", {}))
            print(f"  coverage: incomplete, {n} repo(s) with unverifiable regions")
    return 0 if cert["verdict"] == "MATCH" else 1
