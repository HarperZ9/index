"""Scoring for the navigation benchmark: recall@k, token totals, paired bootstrap.

Pure functions over per-question rows, so the numbers recompute from a results
file without rerunning any arm.
"""
from __future__ import annotations

import random

BENCH_SCHEMA = "index.navigate-bench/v1"


def recall_at_k(ranked_files: list[str], answer: list[str], k: int = 5) -> float:
    """Share of ``answer`` files among the first ``k`` distinct ranked files."""
    if not answer:
        raise ValueError("answer set must not be empty")
    top: list[str] = []
    for path in ranked_files:
        if path not in top:
            top.append(path)
        if len(top) == k:
            break
    return len(set(top) & set(answer)) / len(set(answer))


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def paired_bootstrap(a: list[float], b: list[float], *, resamples: int = 10_000,
                     seed: int = 20261003) -> dict:
    """Mean of (a - b) with a 95% percentile interval, resampling questions in pairs."""
    if len(a) != len(b) or not a:
        raise ValueError("paired samples must be non-empty and the same length")
    rng = random.Random(seed)
    n = len(a)
    diffs = [x - y for x, y in zip(a, b)]
    means = []
    for _ in range(resamples):
        means.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    return {"mean": sum(diffs) / n, "low": _percentile(means, 0.025),
            "high": _percentile(means, 0.975)}


def ratio_bootstrap(a: list[float], b: list[float], *, resamples: int = 10_000,
                    seed: int = 20261003) -> dict:
    """sum(a) / sum(b) with a 95% percentile interval over paired resamples."""
    if len(a) != len(b) or not a:
        raise ValueError("paired samples must be non-empty and the same length")
    rng = random.Random(seed)
    n = len(a)
    ratios = []
    for _ in range(resamples):
        picks = [rng.randrange(n) for _ in range(n)]
        denom = sum(b[i] for i in picks)
        ratios.append(sum(a[i] for i in picks) / denom if denom else float("inf"))
    return {"ratio": sum(a) / sum(b) if sum(b) else float("inf"),
            "low": _percentile(ratios, 0.025), "high": _percentile(ratios, 0.975)}


def verdict(rows: list[dict], arms: list[str], candidate: str = "navigate",
            recall_margin: float = 0.05, token_ratio: float = 0.5) -> dict:
    """Apply the pre-stated bar: recall within ``recall_margin`` of the best other arm at
    no more than ``token_ratio`` of its tokens. Strong pass also needs both intervals.
    Arms tied on recall break toward fewer tokens, which makes the token bar harder."""
    mean = {arm: sum(r[arm]["recall"] for r in rows) / len(rows) for arm in arms}
    others = [a for a in arms if a != candidate]
    tokens = {arm: sum(r[arm]["tokens_shown"] for r in rows) for arm in arms}
    best = min(others, key=lambda a: (-mean[a], tokens[a], others.index(a)))
    rec = paired_bootstrap([r[candidate]["recall"] for r in rows],
                           [r[best]["recall"] for r in rows])
    tok = ratio_bootstrap([r[candidate]["tokens_shown"] for r in rows],
                          [r[best]["tokens_shown"] for r in rows])
    primary = rec["mean"] >= -recall_margin and tok["ratio"] <= token_ratio
    strong = primary and rec["low"] >= -recall_margin and tok["high"] <= token_ratio
    return {"best_arm": best, "mean_recall": mean, "recall_diff": rec, "token_ratio": tok,
            "primary_pass": primary, "strong_pass": strong}
