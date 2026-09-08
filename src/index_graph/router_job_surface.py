"""Shared argument contract for the local router-job CLI and MCP adapters."""
from __future__ import annotations

import json
from pathlib import Path

from . import router_jobs

_OPERATIONS = {
    "status": "read_router_job_status",
    "result": "read_router_job_result",
    "cancel": "cancel_router_job",
    "resume": "resume_router_job",
}


def call_router_job(action: str, args: dict) -> dict:
    if not isinstance(args, dict):
        raise ValueError("router job arguments must be an object")
    allowed = {"root", "max_docs", "budget_ms", "no_cache"} if action == "start" else {"job_id"}
    if set(args) - allowed:
        raise ValueError("unexpected router job arguments")
    if action == "start":
        root = args.get("root")
        if not isinstance(root, str) or not root.strip():
            raise ValueError("root must be a non-empty string")
        values = {key: args.get(key, default) for key, default in
                  (("max_docs", 500), ("budget_ms", 0))}
        for key, value in values.items():
            if type(value) is not int or value < 0:
                raise ValueError(f"{key} must be a non-negative integer")
        no_cache = args.get("no_cache", False)
        if type(no_cache) is not bool:
            raise ValueError("no_cache must be a boolean")
        return router_jobs.start_router_job(Path(root), **values, use_cache=not no_cache)
    if action not in _OPERATIONS:
        raise ValueError("unknown router job operation")
    job_id = args.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job_id must be a non-empty string")
    return getattr(router_jobs, _OPERATIONS[action])(job_id)


def cmd_router_job(args) -> int:
    payload = ({"root": str(args.root), "max_docs": args.max_docs,
                "budget_ms": args.budget_ms, "no_cache": args.no_cache}
               if args.action == "start" else {"job_id": args.job_id})
    try:
        receipt = call_router_job(args.action, payload)
    except (OSError, ValueError, router_jobs.RouterJobError) as exc:
        print(json.dumps({"schema": "index.router-job-error/v1", "status": "failed",
                          "error_type": type(exc).__name__, "message": str(exc)}))
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 1 if receipt.get("status") == "failed" else 0


def tool_definitions() -> list[dict]:
    start_properties = {
        "root": {"type": "string", "minLength": 1},
        "max_docs": {"type": "integer", "minimum": 0, "default": 500},
        "budget_ms": {"type": "integer", "minimum": 0, "default": 0,
                      "description": "Discovery budget; zero permits a complete background scan."},
        "no_cache": {"type": "boolean", "default": False},
    }
    descriptions = {
        "start": "Start a durable local router build and return a job receipt promptly. State and output remain private local files.",
        "status": "Read current router job progress and recovery state.",
        "result": "Retrieve router text only from a complete, validated local job result.",
        "cancel": "Request cooperative cancellation; acknowledgment is reported separately.",
        "resume": "Retry a stopped router job with its original request and fresh discovery.",
    }
    return [{"name": f"index.router.job.{action}", "description": description,
             "inputSchema": {"type": "object", "additionalProperties": False,
                             "properties": start_properties if action == "start" else {
                                 "job_id": {"type": "string", "minLength": 1}},
                             "required": ["root"] if action == "start" else ["job_id"]}}
            for action, description in descriptions.items()]
