"""Single command-line entry point."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from . import __version__
from .config import load_config
from .scan import build_map, write_map


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-repo-map",
        description="Compact JSON repository inventory maps for multi-repo workspaces.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Workspace root. Defaults to the current directory.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path. Defaults to <root>/WORKSPACE-REPO-MAP.json.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    parser.add_argument("--config", type=Path, default=None, help="Path to .repomap.toml.")
    parser.add_argument("--jobs", type=int, default=None, help="Override worker count.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    config = load_config(args.config, root)
    if args.jobs is not None:
        if args.jobs < 1:
            raise SystemExit("--jobs must be a positive integer")
        config = replace(config, jobs=args.jobs)
    if args.json:
        data = build_map(root, config, __version__)
        print(json.dumps(data.to_json(), indent=2))
    else:
        output = args.output.resolve() if args.output else root / "WORKSPACE-REPO-MAP.json"
        data = write_map(root, config, __version__, output)
        print(f"wrote {output}")
        print(f"repos={data.repo_count} dirty={data.dirty_count}")
    return 0
