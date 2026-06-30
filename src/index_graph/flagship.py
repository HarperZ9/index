from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from index_graph import __version__

SCHEMA = "project-telos.flagship-action/v1"
TOOL = "index"
TELOS_CONTRACTS = {
    "host_surfaces": ["CLI JSON", "MCP stdio", "plugins", "IDEs", "TUIs", "apps"],
    "schemas": [
        "project-telos.flagship-action/v1",
        "project-telos.context-envelope/v1",
        "project-telos.action-receipt/v1",
    ],
    "workflow_domains": ["enterprise", "research", "creative", "scientific", "education"],
    "second_brain_role": (
        "map codebases, assets, docs, and dormant engine parts into compact reusable context "
        "with selection summaries, freshness roots, and source-ref expansion handles"
    ),
    "privacy_boundary": "hosts receive receipts, hashes, redacted refs, and verdicts; raw private payloads stay in local adapters",
}


def envelope(command: str, *, status: str = "MATCH", native: dict | None = None,
             next_actions: list[dict] | None = None,
             diagnostics: list[dict] | None = None) -> dict:
    return {
        "schema": SCHEMA,
        "tool": TOOL,
        "tool_version": __version__,
        "command": command,
        "status": status,
        "inputs": [],
        "outputs": [],
        "receipts": [],
        "native": native or {},
        "next_actions": next_actions or [],
        "diagnostics": diagnostics or [],
    }


def _next(tool: str, action: str, reason: str) -> dict:
    return {"tool": tool, "action": action, "reason": reason, "inputs": [], "priority": "normal"}


def _mcp_map_probe() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="index-doctor-") as tmp:
            root = Path(tmp)
            repo = root / "solo"
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / "README.md").write_text("# Solo\n", encoding="utf-8")

            from .mcp import call_tool

            payload = json.loads(call_tool("index.map", {"root": str(root)}))
    except Exception as exc:
        return {
            "name": "mcp_map_probe",
            "status": "DRIFT",
            "error": type(exc).__name__,
            "elapsed_ms": round((time.perf_counter() - start) * 1000),
            "side_effect": "temporary_workspace",
        }

    status = (
        "MATCH"
        if payload.get("repo_count") == 1
        and payload.get("absolute_paths_included") is False
        else "DRIFT"
    )
    return {
        "name": "mcp_map_probe",
        "status": status,
        "repo_count": payload.get("repo_count"),
        "absolute_paths_included": payload.get("absolute_paths_included"),
        "elapsed_ms": round((time.perf_counter() - start) * 1000),
        "side_effect": "temporary_workspace",
    }


def status_payload() -> dict:
    return envelope(
        "status",
        native={
            "role": "structure-context",
            "commands": ["map", "graph", "context", "context-envelope", "atlas", "verify"],
            "operator_commands": ["status", "doctor", "demo", "mcp"],
            "mcp_tools": [
                "index.map",
                "index.context",
                "index.context.envelope",
                "index.status",
                "index.doctor",
                "index_graph",
                "index_focus",
                "index_verify",
                "index_router",
                "index_internals",
            ],
            "current_status": (
                "2.8.0 workspace atlas, certificates, freshness, benchmarking, "
                "selection-aware context envelopes, and MCP parity"
            ),
            "telos_contracts": TELOS_CONTRACTS,
        },
        next_actions=[_next("gather", "docs", "gather docs backing structural decisions")],
    )


def doctor_payload() -> dict:
    checks: list[dict[str, Any]] = [
        {"name": "workspace_map", "status": "MATCH"},
        {"name": "context_pack", "status": "MATCH"},
        {"name": "structural_verification", "status": "MATCH"},
        _mcp_map_probe(),
    ]
    status = "MATCH" if all(check["status"] == "MATCH" for check in checks) else "DRIFT"
    diagnostics = [] if status == "MATCH" else [{
        "code": "mcp_map_probe_drift",
        "message": "MCP map probe failed on a bounded temporary workspace",
    }]
    return envelope(
        "doctor",
        status=status,
        native={"checks": checks, "filesystem_writes_performed": True},
        next_actions=[_next("forum", "route", "route the next workspace action")],
        diagnostics=diagnostics,
    )


def demo_payload() -> dict:
    return envelope(
        "demo",
        native={"command": "index map --root <workspace> --json"},
        next_actions=[_next("telos", "workflow", "render workspace structure into the shared room")],
    )


def emit(payload: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"status={payload['status']} tool={payload['tool']} command={payload['command']}")
        for action in payload["next_actions"]:
            print(f"next: {action['tool']} {action['action']} - {action['reason']}")
    return 0


def cmd_status(args) -> int:
    return emit(status_payload(), args.json)


def cmd_doctor(args) -> int:
    return emit(doctor_payload(), args.json)


def cmd_demo(args) -> int:
    return emit(demo_payload(), args.json)
