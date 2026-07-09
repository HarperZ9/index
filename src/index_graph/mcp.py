"""A zero-dependency, MCP-shaped stdio protocol face for index.

Newline-delimited JSON-RPC 2.0 over stdin/stdout, no SDK and no model. An agent host
connects and calls deterministic tools (graph, focus, verify, router, internals) to
consume index's verified map natively. This is the clean seam a router or orchestrator
composes through: the protocol pillar, not embeddings. Every tool reuses an existing
index function, so the protocol face adds a surface, never a second source of truth.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
from time import time

from . import __version__

_PROTOCOL_VERSION = "2024-11-05"
_CACHE_SCHEMA = "index.mcp-cache-entry/v1"
_CACHE: dict[str, dict] = {}
_CACHEABLE_TOOLS = {
    "index.map",
    "index.context",
    "index.context.envelope",
    "index_graph",
    "index_router",
}


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _tool_error_payload(name: str, args: dict, exc: BaseException) -> str:
    root = args.get("root", "") if isinstance(args, dict) else ""
    payload = {
        "schema": "index.mcp-tool-error/v1",
        "tool": name,
        "status": "UNVERIFIABLE",
        "error_type": type(exc).__name__,
        "message": str(exc),
        "root": str(root),
        "recoverable": not isinstance(exc, (KeyboardInterrupt,)),
        "next_actions": [
            "Inspect the root configuration and filesystem permissions.",
            "Run the matching index CLI command with --json to reproduce outside the MCP host.",
            "If this came from a large workspace scan, reduce focus or add [scan].prune entries.",
        ],
    }
    if os.environ.get("INDEX_MCP_DEBUG_ERRORS") == "1":
        payload["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
    return json.dumps(payload, indent=2, sort_keys=True)


def _cache_ttl_seconds() -> float:
    raw = os.environ.get("INDEX_MCP_CACHE_TTL_SECONDS", "900")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 900.0


def _cache_dir() -> Path:
    raw = os.environ.get("INDEX_MCP_CACHE_DIR")
    if raw:
        return Path(raw)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "index_graph" / "mcp-cache"
    return Path.home() / ".cache" / "index_graph" / "mcp-cache"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _workspace_signature(root: Path) -> str:
    parts = [str(root)]
    for cfg in (root / ".index.toml", root / ".repomap.toml"):
        try:
            stat = cfg.stat()
        except OSError:
            parts.append(f"{cfg.name}:missing")
        else:
            parts.append(f"{cfg.name}:{stat.st_mtime_ns}:{stat.st_size}")
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        parts.append(f"root-error:{type(exc).__name__}:{exc}")
        return _sha256_text("|".join(parts))
    for entry in entries:
        try:
            stat = entry.stat()
        except OSError:
            parts.append(f"{entry.name}:unstatable")
            continue
        kind = "d" if entry.is_dir() else "f"
        parts.append(f"{entry.name}:{kind}:{stat.st_mtime_ns}:{stat.st_size}")
    return _sha256_text("|".join(parts))


def _cache_key(name: str, root: Path, args: dict) -> str:
    stable_args = {
        key: value
        for key, value in args.items()
        if key not in {"root"} and isinstance(value, (str, int, float, bool, type(None), list, dict))
    }
    payload = {
        "tool": name,
        "root": str(root),
        "args": stable_args,
        "workspace_signature": _workspace_signature(root),
        "tool_version": __version__,
    }
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def _cache_path(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def _cache_read(key: str) -> str | None:
    ttl = _cache_ttl_seconds()
    if ttl <= 0:
        return None
    now = time()
    entry = _CACHE.get(key)
    if entry and now - float(entry.get("created_at", 0.0)) <= ttl:
        return str(entry.get("text", ""))
    path = _cache_path(key)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if data.get("schema") != _CACHE_SCHEMA:
        return None
    created_at = float(data.get("created_at", 0.0))
    if now - created_at > ttl:
        return None
    text = str(data.get("text", ""))
    _CACHE[key] = {"created_at": created_at, "text": text}
    return text


def _cache_write(key: str, text: str) -> str:
    ttl = _cache_ttl_seconds()
    if ttl <= 0:
        return text
    entry = {"schema": _CACHE_SCHEMA, "created_at": time(), "text": text}
    _CACHE[key] = {"created_at": entry["created_at"], "text": text}
    try:
        path = _cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, separators=(",", ":")), encoding="utf-8")
    except OSError:
        pass
    return text


def _with_cache(name: str, root: Path, args: dict, build):
    if name not in _CACHEABLE_TOOLS:
        return build()
    key = _cache_key(name, root, args)
    cached = _cache_read(key)
    if cached is not None:
        return cached
    return _cache_write(key, build())


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
        {"name": "index.invalidate",
         "description": "Diff the tree against a pinned fingerprint and name exactly what the changes invalidate (index.invalidation/1). Without 'pin', mints and returns a pin of the current tree, matching the `index invalidate` CLI surface.",
         "inputSchema": _root_schema({
             "pin": {"type": "string", "description": "path to a pin JSON minted earlier"},
         })},
        {"name": "index.wiki",
         "description": "Single-repo verified wiki pack (pages derived from the module graph, sealed manifest, commit-pinned), matching the `index wiki --format json` CLI surface; pass verify=PATH to re-check a sealed artifact (MATCH/DRIFT/UNVERIFIABLE).",
         "inputSchema": _root_schema({
             "verify": {"type": "string",
                        "description": "path to a sealed wiki artifact to verify"},
         })},
        {"name": "index.symbol-graph",
         "description": "Symbol-level call/reference graph for one repo (root IS the repo): function/class/method definitions plus resolved (exact within-module, best-effort cross-module) and honestly-unresolved calls, matching the `index internals-symbols --json` CLI surface.",
         "inputSchema": _root_schema()},
        {"name": "index.symbol-definition",
         "description": "GO-TO-DEFINITION: the file:line of every symbol whose id or bare name matches, derived (never guessed) from the AST.",
         "inputSchema": _root_schema({"symbol": {"type": "string",
                                                 "description": "symbol id (module::name) or bare name"}},
                                     required=["root", "symbol"])},
        {"name": "index.symbol-references",
         "description": "FIND-REFERENCES: every resolved caller of a symbol, each with file:line evidence; unresolved references are reported separately, never as a caller.",
         "inputSchema": _root_schema({"symbol": {"type": "string",
                                                 "description": "symbol id (module::name) or bare name"}},
                                     required=["root", "symbol"])},
        {"name": "index.symbol-implementations",
         "description": "FIND-IMPLEMENTATIONS: in-repo subclasses of a class or overrides of a method, each with file:line evidence and an exact/cross_module resolution label; an external or unbindable base yields no edge (never guessed).",
         "inputSchema": _root_schema({"symbol": {"type": "string",
                                                 "description": "class or method symbol id (module::name / Class::method) or bare name"}},
                                     required=["root", "symbol"])},
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
         "inputSchema": _root_schema({"max_docs": {"type": "integer"}})},
        {"name": "index_internals",
         "description": "Intra-repo module dependency graph for one repo, with cycles and coverage.",
         "inputSchema": _root_schema({"repo": {"type": "string"}}, required=["root", "repo"])},
    ]


def _repo_paths(root: Path) -> dict:
    from .scan import discover_repos
    from .config import load_config
    return {p.name: p for p in discover_repos(root, load_config(None, root))}


def _symbol_matches(sym, query: str) -> bool:
    return sym.id == query or sym.name == query


def _symbol_tool(name: str, root: Path, args: dict) -> str:
    from .symbols import (build_symbol_navigator, find_implementations,
                          symbol_graph_to_payload)
    g, edges = build_symbol_navigator(root)
    if name == "index.symbol-graph":
        return json.dumps(symbol_graph_to_payload(g), indent=2, sort_keys=True)
    query = (args.get("symbol") or "").strip()
    if not query:
        raise ValueError("missing required argument: symbol")
    if name == "index.symbol-implementations":
        impls = find_implementations(g, edges, query)
        return json.dumps({"symbol": query, **impls}, indent=2, sort_keys=True)
    if name == "index.symbol-definition":
        defs = [{"id": s.id, "name": s.name, "kind": s.kind, "file": s.file,
                 "line": s.line, "parent": s.parent}
                for s in g.symbols if _symbol_matches(s, query)]
        return json.dumps({"symbol": query, "definitions": defs},
                          indent=2, sort_keys=True)
    # index.symbol-references: resolved callers + separately, unresolved refs
    targets = {s.id for s in g.symbols if _symbol_matches(s, query)}
    refs = [{"from_symbol": c.from_symbol, "file": c.evidence_file,
             "line": c.evidence_line, "raw": c.raw, "confidence": c.confidence}
            for c in g.calls if c.to_symbol in targets]
    unresolved = [{"from_symbol": c.from_symbol, "to_name": c.to_name,
                   "file": c.evidence_file, "line": c.evidence_line}
                  for c in g.calls if c.to_symbol is None and c.to_name == query]
    return json.dumps({"symbol": query, "references": refs,
                       "unresolved_references": unresolved}, indent=2, sort_keys=True)


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
    from .context.focus import FocusRejection, focus_rejection
    from .context.pack import to_json, closure, preservation, focus_subgraph

    if "root" not in args:
        raise ValueError("missing required argument: root")
    root = Path(args["root"]).resolve()
    if not root.is_dir():
        raise ValueError(f"root not found: {root}")

    if name == "index.wiki":
        # single-repo altitude: the root IS the repo, no workspace scan
        if args.get("verify"):
            from .wiki import run_verify
            return json.dumps(run_verify(Path(args["verify"]), root),
                              indent=2, sort_keys=True)
        from .wiki import build_wiki_pack
        return json.dumps(build_wiki_pack(root), indent=2, sort_keys=True)

    if name in ("index.symbol-graph", "index.symbol-definition",
                "index.symbol-references", "index.symbol-implementations"):
        return _symbol_tool(name, root, args)

    repo_paths = _repo_paths(root)

    if name == "index.invalidate":
        # without 'pin' this mints one; with 'pin' it emits the typed report.
        # both are payloads, matching the CLI's --out / --pin modes.
        from .freshness.invalidate import mint_pin
        from .freshness.invalidate_cli import run_invalidate
        if not args.get("pin"):
            return json.dumps(mint_pin(root), indent=2, sort_keys=True)
        pin_path = Path(args["pin"])
        try:
            pin = json.loads(pin_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read pin {pin_path}: {exc}")
        return json.dumps(run_invalidate(root, pin), indent=2, sort_keys=True)

    if name == "index.map":
        from .config import load_config
        from .scan import build_map
        return _with_cache(
            name,
            root,
            args,
            lambda: json.dumps(
                build_map(root, load_config(None, root), __version__).to_json(),
                indent=2,
                sort_keys=True,
            ),
        )

    if name in ("index.context", "index_graph"):
        return _with_cache(
            name,
            root,
            args,
            lambda: json.dumps(to_json(build_graph(repo_paths)), indent=2, sort_keys=True),
        )

    if name == "index.context.envelope":
        from .context.envelope import build_context_envelope
        def _build_envelope():
            try:
                env = build_context_envelope(
                    build_graph(repo_paths),
                    root=root,
                    token_budget=int(args.get("budget", 1200)),
                    focus=args.get("focus"),
                    hops=args.get("hops"),
                )
            except FocusRejection as exc:
                # an unresolvable focus is a typed receipt, not a protocol error
                # (the index.select not-found precedent)
                return json.dumps(exc.receipt, indent=2, sort_keys=True)
            return json.dumps(env, indent=2, sort_keys=True)
        return _with_cache(name, root, args, _build_envelope)

    if name == "index_focus":
        graph = build_graph(repo_paths)
        repo = args.get("repo") or ""
        names = {n.name for n in graph.repos}
        if repo not in names:
            return json.dumps(focus_rejection(repo, names), indent=2, sort_keys=True)
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
        max_docs = max(0, int(args.get("max_docs", 500)))
        return _with_cache(
            name,
            root,
            args,
            lambda: render_router(build_router_pack(
                build_graph(repo_paths),
                discover_docs(root),
                repo_dirs,
            ), max_docs=max_docs),
        )

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
        except BaseException as exc:
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": _tool_error_payload(name, args, exc)}],
                               "isError": True}}
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def _decode_line(line) -> str:
    if isinstance(line, bytes):
        return line.decode("utf-8", "replace")
    return str(line)


def _read_framed_body(first_line, stdin) -> str | None:
    header = _decode_line(first_line).strip()
    try:
        length = int(header.split(":", 1)[1].strip())
    except (IndexError, ValueError):
        return None
    while True:
        line = stdin.readline()
        if line in ("", b""):
            return None
        if _decode_line(line).strip() == "":
            break
    body = stdin.read(length)
    if body in ("", b""):
        return None
    if isinstance(body, bytes):
        return body.decode("utf-8", "replace")
    return str(body)


def _write_response(stdout, resp: dict, framed: bool) -> None:
    body = json.dumps(resp)
    if not framed:
        stdout.write(body + "\n")
        stdout.flush()
        return
    payload = body.encode("utf-8")
    frame = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload
    buffer = getattr(stdout, "buffer", None)
    if buffer is not None:
        buffer.write(frame)
        buffer.flush()
        return
    stdout.write(frame.decode("utf-8"))
    stdout.flush()


def serve(stdin=None, stdout=None) -> int:
    """Read MCP stdio frames or newline-delimited JSON-RPC from stdin."""
    _configure_stdio()
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    reader = getattr(stdin, "buffer", stdin)
    while True:
        line = reader.readline()
        if line in ("", b""):
            break
        text = _decode_line(line).strip()
        framed = text.lower().startswith("content-length:")
        if framed:
            text = _read_framed_body(line, reader)
            if text is None:
                continue
        else:
            text = text.strip()
        if not line:
            continue
        try:
            req = json.loads(text)
        except json.JSONDecodeError:
            continue  # no id to address a parse error to; conformant hosts send valid frames
        resp = handle_request(req)
        if resp is not None:
            _write_response(stdout, resp, framed)
    return 0
