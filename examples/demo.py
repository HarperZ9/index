#!/usr/bin/env python3
# Best-effort demo — not runtime-verified by author.
"""End-to-end demo for index.

Builds a throwaway workspace with two git repos in a temp dir, then exercises the
real public API (`build_map`, `default_config`, `classify`) and the CLI module
(`python -m index_graph`). Everything used here exists in the package; no
flags or functions are invented.

Run:
    python examples/demo.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from index_graph import __version__, build_map, classify, default_config


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _make_repo(path: Path, *, origin: str | None, marker: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "demo@example.com")
    _git(path, "config", "user.name", "demo")
    (path / marker).write_text("demo\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")
    if origin is not None:
        _git(path, "remote", "add", "origin", origin)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="index-demo-") as tmp:
        root = Path(tmp)
        _make_repo(root / "proj-a", origin="https://github.com/example/proj-a.git",
                   marker="README.md")
        _make_repo(root / "proj-b", origin=None, marker="pyproject.toml")

        config = default_config()

        # 1) Importable API: build the map in-process.
        print("== build_map ==")
        m = build_map(root, config, __version__)
        print(f"repo_count={m.repo_count} dirty_count={m.dirty_count}")
        print(f"class_counts={m.class_counts}")
        for row in m.repositories:
            print(f"  {row.path:8} {row.class_:8} {row.branch} {row.head} "
                  f"markers={list(row.markers)}")

        # 2) Pure classification helper.
        print("\n== classify ==")
        print("proj-a ->", classify("proj-a", True,
                                     "https://github.com/example/proj-a.git", config))
        print("proj-b ->", classify("proj-b", True, "", config))

        # 3) CLI module: print JSON to stdout exactly as the console script would.
        print("\n== python -m index_graph --json ==")
        result = subprocess.run(
            [sys.executable, "-m", "index_graph", "--root", str(root), "--json"],
            text=True, capture_output=True, check=True,
        )
        payload = json.loads(result.stdout)
        print(f"schema_version={payload['schema_version']} "
              f"tool_version={payload['tool_version']} "
              f"repo_count={payload['repo_count']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
