from __future__ import annotations

import argparse

from . import map


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build workspace repository map")
    parser.add_argument("--root", type=str, default=".")
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = map.Path(args.output) if args.output else None
    return map.main(["--root", args.root, *( ["--output", args.output] if args.output else [] ), *( ["--json"] if args.json else [] )])


if __name__ == "__main__":
    raise SystemExit(main())