"""Dogfood: run the graph engine over a corpus and report edge recovery.

Compares the engine's inferred internal edges against a hand-authored edge set
(if available) and prints recall + false-positive counts. Read-only; no writes.

Usage:
    python scripts/dogfood_recovery.py --root C:/dev [--truth path/to/edges.json]

--truth is an optional JSON list of {"from": repo, "to": repo} hand-authored edges.
Without it, the harness just prints the inferred graph summary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from index_graph.config import load_config
from index_graph.graph.build import build_graph
from index_graph.scan import discover_repos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--truth", type=Path, default=None)
    args = ap.parse_args(argv)

    root = args.root.resolve()
    paths = {p.name: p for p in discover_repos(root, load_config(None, root))}
    graph = build_graph(paths)
    inferred = {(e.from_repo, e.to_repo) for e in graph.edges if not e.external}
    print(f"repos={len(graph.repos)} internal_edges={len(inferred)} "
          f"external_edges={sum(1 for e in graph.edges if e.external)} "
          f"warnings={len(graph.warnings)}")

    if args.truth and args.truth.is_file():
        truth = {(d["from"], d["to"]) for d in json.loads(args.truth.read_text("utf-8"))}
        recovered = inferred & truth
        missed = truth - inferred
        extra = inferred - truth
        recall = len(recovered) / len(truth) if truth else 0.0
        print(f"truth_edges={len(truth)} recovered={len(recovered)} "
              f"recall={recall:.0%} missed={len(missed)} new_inferred={len(extra)}")
        if missed:
            print("missed (hand-authored, not inferred):")
            for a, b in sorted(missed):
                print(f"  {a} -> {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
