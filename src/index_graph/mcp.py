"""A zero-dependency, MCP-shaped stdio protocol face for index.

Newline-delimited JSON-RPC 2.0 over stdin/stdout, no SDK and no model. An agent host
connects and calls deterministic tools (graph, focus, verify, router, internals) to
consume index's verified map natively. This is the clean seam a router or orchestrator
composes through: the protocol pillar, not embeddings. Every tool reuses an existing
index function, so the protocol face adds a surface, never a second source of truth.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import __version__

_PROTOCOL_VERSION = "2024-11-05"


def _root_schema(extra: dict | None = None, required: list | None = None) -> dict:
    props = {"root": {"type": "string", "description": "workspace root path"}}
    if extra:
        props.update(extra)
    return {"type": "object", "properties": props, "required": required or ["root"]}


def _tool_defs() -> list[dict]:
    return [
        {"name": "index.map",
         "description": "Repository inventory map as JSON, matching the `index map --json` CLI surface.",
         "inputSchema": _root_schema()},
        {"name": "index.context",
         "description": "Repo-level dependency context pack as JSON, matching the `index context --json` CLI surface.",
         "inputSchema": _root_schema()},
        {"name": "index.context.envelope",
         "description": "Budgeted, receipt-backed context envelope for large-codebase agent workflows.",
         "inputSchema": _root_schema({
             "budget": {"type": "integer"},
             "focus": {"type": "string"},
             "hops": {"type": "integer"},
         })},
        {"name": "index.select",
         "description": "Path selection with typed rejection receipts; candidates reconcile to selected + rejected, matching the `index select --json` CLI surface.",
         "inputSchema": _root_schema({
             "suffixes": {"type": "array", "items": {"type": "string"}},
             "max_files": {"type": "integer"},
         })},
        {"name": "index.status",
         "description": "Project Telos operator-spine status action envelope, matching the `index status --json` CLI surface.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "index.doctor",
         "description": "Project Telos operator-spine readiness checks action envelope, matching the `index doctor --json` CLI surface.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "index_graph",
         "description": "Repo-level dependency graph (relations, roles, cycles) as JSON.",
         "inputSchema": _root_schema()},
        {"name": "index_focus",
         "description": "A repo's dependency neighborhood plus a preservation manifest of what was dropped at the boundary.",
         "inputSchema": _root_schema({"repo": {"type": "string"}, "hops": {"type": "integer"}},
                                     required=["root", "repo"])},
        {"name": "index_verify",
         "description": "Ground a structural claim. Pass depends 'A -> B' or exists 'NAME'. Returns MATCH/REFUTED/UNVERIFIABLE with file:line evidence.",
         "inputSchema": _root_schema({"depends": {"type": "string"}, "exists": {"type": "string"}})},
        {"name": "index_router",
         "description": "A deterministic CLAUDE.md/AGENTS.md workspace map derived from the graph and docs.",
         "inputSchema": _root_schema()},
        {"name": "index_internals",
         "description": "Intra-repo module dependency graph for one repo, with cycles and coverage.",
         "inputSchema": _root_schema({"repo": {"type": "string"}}, required=["root", "repo"])},
    ]


def _repo_paths(root: Path) -> dict:
    from .scan import discover_repos
    from .config import load_config
    return {p.name: p for p in discover_repos(root, load_config(None, root))}


def call_tool(name: str, args: dict) -> str:
    if name == "index.status":
        from .flagship import status_payload
        return json.dumps(status_payload(), indent=2, sort_keys=True)

    if name == "index.doctor":
        from .flagship import doctor_payload
        return json.dumps(doctor_payload(), indent=2, sort_keys=True)

    if name == "index.select":
        # a missing root yields a not-found receipt (CLI parity), not an error
        from .context.select import run_select
        if "root" not in args:
            raise ValueError("missing required argument: root")
        suffixes = tuple(args["suffixes"]) if args.get("suffixes") else None
        payload = run_select(Path(args["root"]), suffixes, args.get("max_files"))
        return json.dumps(payload, indent=2, sort_keys=True)

    from .graph.build import build_graph
    from .context.pack import to_json, closure, preservation, focus_subgraph

    if "root" not in args:
        raise ValueError("missing required argument: root")
    root = Path(args["root"]).resolve()
    if not root.is_dir():
        raise ValueError(f"root not found: {root}")
    repo_paths = _repo_paths(root)

    if name == "index.map":
        from .config import load_config
        from .scan import build_map
        return json.dumps(build_map(root, load_config(None, root), __version__).to_json(),
                          indent=2, sort_keys=True)

    if name in ("index.context", "index_graph"):
        return json.dumps(to_json(build_graph(repo_paths)), indent=2, sort_keys=True)

    if name == "index.context.envelope":
        from .context.envelope import build_context_envelope
        env = build_context_envelope(
            build_graph(repo_paths),
            root=root,
            token_budget=int(args.get("budget", 1200)),
            focus=args.get("focus"),
            hops=args.get("hops"),
        )
        return json.dumps(env, indent=2, sort_keys=True)

    if name == "index_focus":
        graph = build_graph(repo_paths)
        repo = args.get("repo")
        if repo not in {n.name for n in graph.repos}:
            raise ValueError(f"unknown repo: {repo}")
        hops = args.get("hops")
        keep = closure(list(graph.edges), repo, hops=hops)
        pack = to_json(focus_subgraph(graph, keep))
        pack["preserved"] = preservation(list(graph.edges), keep, repo, hops)
        return json.dumps(pack, indent=2, sort_keys=True)

    if name == "index_verify":
        from .verify import build_verification
        pack = to_json(build_graph(repo_paths))
        if args.get("depends"):
            if "->" not in args["depends"]:
                raise ValueError("depends must be 'A -> B'")
            frm, _, to = args["depends"].partition("->")
            claim = {"kind": "depends", "from": frm.strip(), "to": to.strip()}
        elif args.get("exists"):
            claim = {"kind": "exists", "name": args["exists"].strip()}
        else:
            raise ValueError("index_verify needs 'depends' or 'exists'")
        rec = build_verification(pack, claim, tool_version=__version__,
                                 recheck="index verify (via mcp)")
        return json.dumps(rec, indent=2, sort_keys=True)

    if name == "index_router":
        from .knowledge.atlas import build_router_pack
        from .knowledge.docs import discover_docs
        from .router import render_router

        def _rel(p: Path) -> str:
            r = p.resolve().relative_to(root).as_posix()
            return "" if r == "." else r

        repo_dirs = {nm: _rel(p) for nm, p in repo_paths.items()}
        pack = build_router_pack(build_graph(repo_paths), discover_docs(root), repo_dirs)
        return render_router(pack)

    if name == "index_internals":
        from .internals import build_internals
        repo = args.get("repo")
        if repo not in repo_paths:
            raise ValueError(f"unknown repo: {repo}")
        g = build_internals(repo_paths[repo], repo)
        payload = {
            "repo": g.repo,
            "modules": [{"id": m.id, "path": m.path, "language": m.language} for m in g.modules],
            "edges": [{"from": e.from_id, "to": e.to_id, "file": e.evidence_file,
                       "line": e.evidence_line, "raw": e.raw} for e in g.edges],
            "cycles": [list(c) for c in g.cycles],
            "fan_in": g.fan_in, "fan_out": g.fan_out,
            "coverage": {"complete": g.coverage.complete,
                         "modules": g.coverage.modules,
                         "internal_edges": g.coverage.internal_edges,
                         "parse_errors": list(g.coverage.parse_errors),
                         "dynamic_imports": [{"file": f, "line": ln}
                                             for f, ln in g.coverage.dynamic_imports]},
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    raise ValueError(f"unknown tool: {name}")


def handle_request(req: dict) -> dict | None:
    """Handle one JSON-RPC request; return the response dict, or None for a notification."""
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "index-graph", "version": __version__}}}
    if rid is None:
        return None  # a notification (e.g. notifications/initialized): no response
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": _tool_defs()}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in {t["name"] for t in _tool_defs()}:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"unknown tool: {name!r}"}}
        try:
            text = call_tool(name, args)
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": text}], "isError": False}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": f"error: {exc}"}],
                               "isError": True}}
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> int:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue  # no id to address a parse error to; conformant hosts send valid frames
        resp = handle_request(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0
