"""Start and poll a durable local Index router job.

Usage:
    python examples/router_job_flow.py /path/to/workspace

This example prints status receipts and does not print the router markdown unless
--print-result is passed.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from index_graph.router_jobs import (
    read_router_job_result,
    read_router_job_status,
    start_router_job,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a durable local router job")
    parser.add_argument("root", type=Path, help="workspace root to map")
    parser.add_argument("--max-docs", type=int, default=500)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--print-result", action="store_true")
    args = parser.parse_args()

    started = start_router_job(args.root, max_docs=args.max_docs)
    print(json.dumps({"event": "started", "status": started}, indent=2, sort_keys=True))

    deadline = time.monotonic() + max(0.0, args.timeout_seconds)
    status = started
    while (
        status.get("status") in {"running", "cancellation_requested"}
        and time.monotonic() < deadline
    ):
        time.sleep(max(0.1, args.poll_seconds))
        status = read_router_job_status(started["job_id"])
        print(json.dumps({"event": "status", "status": status}, indent=2, sort_keys=True))

    result = read_router_job_result(started["job_id"])
    if result.get("status") == "complete" and args.print_result:
        print(result["content"])
    else:
        print(json.dumps({"event": "result", "result": result}, indent=2, sort_keys=True))
    return 0 if result.get("status") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
