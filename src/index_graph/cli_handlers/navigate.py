"""Handlers for `index navigate` and `index outline-map`.

`index navigate ROOT "question"` walks the repository one level at a time and
prints the leaves it reached. `index outline-map ROOT --node ID` prints the
children of one node as a map, so a host model can do the choosing itself.
"""
from __future__ import annotations

import json

from ..navigate.api import outline_map, run_navigate
from ._common import require_dir


def cmd_navigate(args) -> int:
    root = require_dir(args.root)
    payload = run_navigate(root, args.query, max_files=args.files, beam=args.beam,
                           ratio=args.ratio, include_docs=args.include_docs,
                           all_leaves=args.all_leaves, with_text=args.json)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["leaves"] else 2
    print(f"navigate files={len(payload['files'])} questions={len(payload['path']['steps'])} "
          f"tokens_shown={payload['tokens_shown']}")
    for leaf in payload["leaves"]:
        print(f"  {leaf['file']}:{leaf['start']}-{leaf['end']}  {leaf['id'].split('::', 1)[-1]}"
              f"  p={leaf['probability']:.3f}")
    return 0 if payload["leaves"] else 2


def cmd_outline_map(args) -> int:
    root = require_dir(args.root)
    try:
        payload = outline_map(root, args.node, include_docs=args.include_docs)
    except KeyError as exc:
        raise SystemExit(exc.args[0]) from None
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(f"outline-map node={payload['node']} kind={payload['kind']} "
          f"entries={len(payload['entries'])}")
    for entry in payload["entries"]:
        print(f"  {entry['name']}  ->  {entry['handle']['node']}")
    return 0


def add_navigate_parsers(sub) -> None:
    """Register `navigate` and `outline-map` (kept here so cli_parser stays small)."""
    from pathlib import Path

    n = sub.add_parser("navigate", help="Find the code for a question by walking the repo "
                       "one level at a time; only the leaves reached are shown.")
    n.add_argument("root", type=Path, help="repository root")
    n.add_argument("query", help="the question, in plain words")
    n.add_argument("--files", type=int, default=5, help="stop after this many files (default 5)")
    n.add_argument("--beam", type=int, default=4, help="most children followed per level")
    n.add_argument("--ratio", type=float, default=0.5,
                   help="follow children at least this share of the top child's probability")
    n.add_argument("--include-docs", action="store_true",
                   help="also walk prose and config files (code only by default)")
    n.add_argument("--all-leaves", action="store_true",
                   help="show every leaf reached, not only the best leaf per file")
    n.add_argument("--json", action="store_true", help="print leaves with source text and the "
                   "decision path as JSON")
    m = sub.add_parser("outline-map", help="Print one outline node's children as a map: a name "
                       "and description to choose from, and the node id to go down to.")
    m.add_argument("root", type=Path, help="repository root")
    m.add_argument("--node", default="", help="node id from a previous map (default: the root)")
    m.add_argument("--include-docs", action="store_true")
    m.add_argument("--json", action="store_true")
