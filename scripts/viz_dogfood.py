"""Opt-in acceptance: render a real workspace and report shape + timing.

Usage: python scripts/viz_dogfood.py <root> <out-dir>
Not part of the unit slice; a manual validation that the renderers run on an
arbitrary corpus and produce a self-contained dashboard.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from workspace_repo_map.cli import main


def run(root: str, out_dir: str) -> int:
    t0 = time.perf_counter()
    rc = main(["viz", "--root", root, "--format", "all", "--out-dir", out_dir])
    dt = time.perf_counter() - t0
    html = Path(out_dir) / "graph.html"
    size = html.stat().st_size if html.exists() else 0
    print(f"rc={rc} wrote={out_dir} html_bytes={size} seconds={dt:.2f}")
    return rc


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(run(sys.argv[1], sys.argv[2]))
