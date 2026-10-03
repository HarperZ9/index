"""Rebuild the frozen navigation query sets from merged pull requests.

Inputs: `prs-<repo>.json` from
`gh pr list -R HarperZ9/<repo> --state merged --limit 200 --json number,title,mergeCommit,mergedAt`
and one clone per repo under --repos-root. Output: the two query files beside
this script. The rules match the decision record: the PR title (conventional
prefix stripped) is the question; the answer is the set of `.py` files the PR
modified, tests excluded, 1 to 8 files; titles naming release, bump or version
are skipped; 20 most recent per repo, with a repo's shortfall filled from the
largest pool.

    python benchmarks/navigate/build_queries.py --repos-root ..
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SKIP = re.compile(r"\b(release|bump|version)\b|^v?\d+\.\d+", re.I)
PREFIX = re.compile(r"^[a-z]+(\([^)]*\))?!?:\s*", re.I)


def git(root: Path, repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root / repo), *args], check=True,
                          capture_output=True, text=True).stdout


def answer_files(root: Path, repo: str, base: str, merge: str) -> list[str]:
    rows = [line.split("\t") for line in git(root, repo, "diff", "--name-status",
                                             base, merge).splitlines()]
    return sorted(r[1] for r in rows if r[0] == "M" and r[1].endswith(".py")
                  and not r[1].startswith("tests/") and "/tests/" not in r[1]
                  and not Path(r[1]).name.startswith("test_"))


def eligible(root: Path, repo: str) -> list[dict]:
    prs = json.loads((HERE / f"prs-{repo}.json").read_text(encoding="utf-8"))
    prs.sort(key=lambda p: p["mergedAt"], reverse=True)
    out = []
    for p in prs:
        merge = (p.get("mergeCommit") or {}).get("oid")
        if not merge or SKIP.search(p["title"]):
            continue
        try:
            parents = git(root, repo, "rev-list", "--parents", "-n", "1", merge).split()
        except subprocess.CalledProcessError:
            print("missing commit", repo, p["number"], file=sys.stderr)
            continue
        if len(parents) < 2:
            continue
        answer = answer_files(root, repo, parents[1], merge)
        if 1 <= len(answer) <= 8:
            out.append({"repo": repo, "pr": p["number"], "query": PREFIX.sub("", p["title"]).strip(),
                        "base": parents[1], "merge": merge, "answer": answer})
    return out


def pick(held: dict[str, list[dict]], total: int = 60, per_repo: int = 20) -> list[dict]:
    quota = {r: min(per_repo, len(v)) for r, v in held.items()}
    short = total - sum(quota.values())
    for r in sorted(held, key=lambda r: -len(held[r])):
        extra = min(short, len(held[r]) - quota[r])
        quota[r] += extra
        short -= extra
    return [row for r, rows in held.items() for row in rows[:quota[r]]]


def write(name: str, rows: list[dict]) -> None:
    body = json.dumps({"schema": "index.navigate-queries/v1", "rows": rows}, indent=1, sort_keys=True)
    (HERE / name).write_text(body + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos-root", type=Path, required=True)
    root = ap.parse_args().repos_root
    held = {r: eligible(root, r) for r in ("index", "crucible", "gather")}
    write("queries-heldout-v1.json", pick(held))
    write("queries-design-v1.json", eligible(root, "mneme")[:20])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
