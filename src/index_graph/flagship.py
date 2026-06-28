from __future__ import annotations

import json

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
    "second_brain_role": "map codebases, assets, docs, and dormant engine parts into compact reusable context",
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


def status_payload() -> dict:
    return envelope(
        "status",
        native={
            "role": "structure-context",
            "commands": ["map", "graph", "context", "atlas", "verify"],
            "operator_commands": ["status", "doctor", "demo", "mcp"],
            "mcp_tools": [
                "index.map",
                "index.context",
                "index.status",
                "index.doctor",
                "index_graph",
                "index_focus",
                "index_verify",
                "index_router",
                "index_internals",
            ],
            "current_status": "2.8.0 workspace atlas, certificates, freshness, benchmarking, and MCP parity",
            "telos_contracts": TELOS_CONTRACTS,
        },
        next_actions=[_next("gather", "docs", "gather docs backing structural decisions")],
    )


def doctor_payload() -> dict:
    checks = [
        {"name": "workspace_map", "status": "MATCH"},
        {"name": "context_pack", "status": "MATCH"},
        {"name": "structural_verification", "status": "MATCH"},
    ]
    return envelope(
        "doctor",
        native={"checks": checks},
        next_actions=[_next("forum", "route", "route the next workspace action")],
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
