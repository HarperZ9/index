"""Run the navigation benchmark over a frozen query file.

Each question is answered against its repository at the PR's base commit,
extracted with ``git archive``. Usage:

    python scripts/navigate_bench.py --queries benchmarks/navigate/queries-heldout-v1.json \
        --repos-root ../ --cache .navigate-cache --out results.json

``--repos-root`` holds one clone per repo name in the query file.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from index_graph.navigate.arms import (bm25_chunk_arm, bm25_chunk_best_arm,  # noqa: E402
                                       bm25_file_arm, grep_arm, map_arm, navigate_arm)
from index_graph.navigate.bench import BENCH_SCHEMA, recall_at_k, verdict  # noqa: E402
from index_graph.navigate.chooser import LexicalChooser  # noqa: E402
from index_graph.navigate.outline import build_outline  # noqa: E402

ARMS = ["grep", "bm25-file", "bm25-chunk", "bm25-chunk-best", "map", "navigate"]


def snapshot(repos_root: Path, cache: Path, repo: str, sha: str) -> Path:
    target = cache / f"{repo}-{sha[:12]}"
    if not (target / ".complete").exists():
        data = subprocess.run(["git", "-C", str(repos_root / repo), "archive", "--format=tar", sha],
                              check=True, capture_output=True).stdout
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(target, filter="data")
        (target / ".complete").write_text(sha)
    return target


def run_question(row: dict, outline, args) -> dict:
    chooser = LexicalChooser(outline.idf, temperature=args.temperature)
    query = row["query"]
    results = {
        "grep": grep_arm(outline, query),
        "bm25-file": bm25_file_arm(outline, query),
        "bm25-chunk": bm25_chunk_arm(outline, query),
        "bm25-chunk-best": bm25_chunk_best_arm(outline, query),
        "map": map_arm(outline, query, chooser),
        "navigate": navigate_arm(outline, query, chooser, ratio=args.ratio, beam=args.beam),
    }
    out = {"repo": row["repo"], "pr": row["pr"]}
    for arm, res in results.items():
        out[arm] = {"recall": recall_at_k(res["files"], row["answer"]),
                    "tokens_shown": res["tokens_shown"],
                    "question_tokens": res["question_tokens"], "files": res["files"]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=Path, required=True)
    ap.add_argument("--repos-root", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--ratio", type=float, default=0.5)
    ap.add_argument("--beam", type=int, default=4)
    args = ap.parse_args()
    raw = args.queries.read_bytes()
    rows = json.loads(raw)["rows"]
    outlines: dict[tuple[str, str], object] = {}
    scored = []
    for row in rows:
        key = (row["repo"], row["base"])
        if key not in outlines:
            outlines[key] = build_outline(snapshot(args.repos_root, args.cache, *key))
        scored.append(run_question(row, outlines[key], args))
    report = {"schema": BENCH_SCHEMA, "queries_sha256": hashlib.sha256(raw).hexdigest(),
              "params": {"temperature": args.temperature, "ratio": args.ratio, "beam": args.beam},
              "verdict": verdict(scored, ARMS), "rows": scored}
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                        newline="\n")
    v = report["verdict"]
    for arm in ARMS:
        tokens = sum(r[arm]["tokens_shown"] for r in scored)
        print(f"{arm:15s} recall@5={v['mean_recall'][arm]:.3f} tokens={tokens}")
    print(json.dumps({k: v[k] for k in ("best_arm", "recall_diff", "token_ratio",
                                        "primary_pass", "strong_pass")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
