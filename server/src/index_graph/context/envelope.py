"""Budgeted context envelopes for large-codebase agent work."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from ..freshness import SCHEMA as FRESHNESS_SCHEMA, workspace_fingerprint
from ..graph.build import DependencyGraph
from .focus import resolve_focus
from .pack import closure, focus_subgraph, preservation, to_json

SCHEMA = "project-telos.context-envelope/v1"
TOOL = "index.context.envelope"
BYTES_PER_TOKEN = 4
FRESHNESS_ENVELOPE_SCHEMA = "index.context-envelope-freshness/v1"


def build_context_envelope(
    graph: DependencyGraph,
    *,
    root: Path | str,
    token_budget: int,
    focus: str | None = None,
    hops: int | None = None,
    browser_evidence_refs: list[dict] | None = None,
    bounded_output: bool = False,
    bounded_output_transport: str = "canonical_json",
    mcp_response_id: object | None = None,
) -> dict:
    """Return a deterministic, receipt-backed context packet within ``token_budget``."""
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    source_graph = graph
    preserved = None
    candidate_repo_count = len(source_graph.repos)
    if focus:
        names = {node.name for node in graph.repos}
        # an unresolvable selector raises FocusRejection (a ValueError) whose
        # .receipt is the typed index.focus-rejection/v1 contract
        focus = resolve_focus(focus, names)
        keep = closure(list(graph.edges), focus, hops=hops)
        preserved = preservation(list(graph.edges), keep, focus, hops)
        graph = focus_subgraph(graph, keep)
    pack = to_json(graph)
    pack_hash = _sha(pack)
    retained: list[dict] = []
    omitted: list[dict] = []
    approx_tokens = _base_tokens(pack)
    source_refs = _source_refs(graph, Path(root).resolve())
    for repo in _ranked_repos(pack, focus):
        item = _repo_item(repo, pack, source_refs.get(repo["name"], []))
        cost = _approx_tokens(item)
        if approx_tokens + cost <= token_budget or not retained:
            retained.append(item)
            approx_tokens += cost
        else:
            omitted.append(_omitted(repo["name"], "budget_exceeded", cost))
    omitted.extend(_focus_omissions(source_graph, graph))
    omitted = _dedupe_omitted(omitted)
    failure_codes = ["budget_exceeded"] if any(
        item["reason"] == "budget_exceeded" for item in omitted
    ) else []
    # if what was KEPT still exceeds the budget (a forced-first item larger
    # than the whole budget, retained because dropping it would return
    # nothing), that is a distinct honest fact from budget_exceeded omissions:
    # the request could not be met even after omitting everything omittable.
    # Name it rather than hiding it behind a min() cap on the reported cost.
    if approx_tokens > token_budget:
        failure_codes.append("budget_overflow")
    verdict = "UNVERIFIABLE" if failure_codes else "MATCH"
    fresh = _freshness(source_graph, retained)
    envelope = {
        "schema": SCHEMA,
        "tool": TOOL,
        "verification_verdict": verdict,
        "failure_codes": failure_codes,
        "root": str(Path(root)),
        "focus": {"repo": focus, "hops": hops},
        "budget": {
            "token_budget": token_budget,
            # approx_tokens bounds the RETAINED selection (base + kept items):
            # that is what the budget gates. It is NOT the whole emitted packet,
            # which also carries omitted/preserved/freshness/selection metadata;
            # packet_approx_tokens (set below) reports the full serialized cost
            # so neither number is read as the other.
            "approx_tokens": approx_tokens,
            "bytes_per_token": BYTES_PER_TOKEN,
        },
        "selection": _selection(
            mode="focused" if focus else "workspace",
            candidate_repo_count=candidate_repo_count,
            selected_repo_count=len(graph.repos),
            retained=retained,
            omitted=omitted,
        ),
        "context_policy": {
            "mode": "lossless_by_reference",
            "raw_payload_policy": "source_refs_only",
            "omission_policy": "explicit_failure_codes",
        },
        "browser_evidence_refs": _browser_evidence_refs(browser_evidence_refs or []),
        "retained": retained,
        "omitted": omitted,
        "preserved": preserved,
        "freshness": fresh,
        "receipts": [{"kind": "graph-pack", "sha256": pack_hash, "schema": "index.context/graph-pack"}],
        "privacy": {"raw_source_included": False, "source_refs_only": True},
        "recheck": {
            "command": "index context-envelope --json",
            "graph_pack_sha256": pack_hash,
            "freshness_root_sha256": fresh["workspace_root_sha256"],
        },
    }
    # the whole emitted packet's approximate token cost (retained content plus
    # all the metadata the caller receives), re-derivable from the dict itself
    packet_bytes = len(json.dumps(envelope, sort_keys=True).encode("utf-8"))
    envelope["budget"]["packet_approx_tokens"] = packet_bytes // BYTES_PER_TOKEN
    if bounded_output:
        envelope = _apply_bounded_output(
            envelope,
            token_budget=token_budget,
            root=Path(root),
            focus=focus,
            hops=hops,
            transport=bounded_output_transport,
            mcp_response_id=mcp_response_id,
        )
    return envelope


def _apply_bounded_output(
    envelope: dict,
    *,
    token_budget: int,
    root: Path,
    focus: str | None,
    hops: int | None,
    transport: str,
    mcp_response_id: object | None,
) -> dict:
    """Compact an envelope so the serialized tool response fits the budget.

    The default contract budgets the retained selection. This opt-in contract
    budgets the emitted JSON packet itself, measured by serialized UTF-8 bytes
    divided by ``BYTES_PER_TOKEN`` and rounded up. That is a deterministic
    transport-size heuristic, not model-tokenizer output.
    """
    if token_budget < 2:
        raise ValueError("bounded_output budget too small to emit overflow receipt")
    envelope["context_policy"]["output_policy"] = "bounded_packet"
    envelope["budget"]["output_policy"] = "bounded_packet"
    envelope["budget"]["pre_compaction_packet_approx_tokens"] = _packet_tokens(
        envelope, ceiling=True, transport=transport, mcp_response_id=mcp_response_id)
    envelope["source_ref_omissions"] = []
    _set_packet_measurement(envelope, transport=transport, mcp_response_id=mcp_response_id)
    if envelope["budget"]["packet_approx_tokens"] <= token_budget:
        return envelope

    _compact_source_refs(
        envelope,
        root=root,
        focus=focus,
        hops=hops,
        token_budget=token_budget,
    )
    _add_failure_code(envelope, "output_budget_exceeded")
    envelope["verification_verdict"] = "UNVERIFIABLE"
    _refresh_selection(envelope)
    _set_packet_measurement(envelope, transport=transport, mcp_response_id=mcp_response_id)
    if envelope["budget"]["packet_approx_tokens"] <= token_budget:
        return envelope

    minimal = _minimal_bounded_overflow_receipt(
        envelope,
        root=root,
        focus=focus,
        hops=hops,
        token_budget=token_budget,
    )
    _set_packet_measurement(minimal, transport=transport, mcp_response_id=mcp_response_id)
    if minimal["budget"]["packet_approx_tokens"] > token_budget:
        raise ValueError("bounded_output budget too small to emit overflow receipt")
    return minimal


def _compact_source_refs(
    envelope: dict,
    *,
    root: Path,
    focus: str | None,
    hops: int | None,
    token_budget: int,
) -> None:
    retained_hashes = envelope.get("freshness", {}).get("retained_repo_sha256", {})
    omissions = []
    pre_compaction = envelope["budget"]["pre_compaction_packet_approx_tokens"]
    for item in envelope.get("retained", []):
        refs = list(item.get("source_refs") or [])
        if not refs:
            continue
        item["source_refs"] = []
        omissions.append(_source_ref_omission(
            item,
            original_source_refs=refs,
            included_source_refs=[],
            root=root,
            focus=focus,
            hops=hops,
            token_budget=token_budget,
            pre_compaction_packet_approx_tokens=pre_compaction,
            retained_repo_sha256=retained_hashes.get(item.get("name")),
        ))
    envelope["source_ref_omissions"] = omissions


def _source_ref_omission(
    item: dict,
    *,
    original_source_refs: list[dict],
    included_source_refs: list[dict],
    root: Path,
    focus: str | None,
    hops: int | None,
    token_budget: int,
    pre_compaction_packet_approx_tokens: int,
    retained_repo_sha256: str | None,
) -> dict:
    omitted = len(original_source_refs) - len(included_source_refs)
    args = {
        "root": str(root),
        "budget": max(token_budget, pre_compaction_packet_approx_tokens),
        "bounded_output": False,
    }
    if focus is not None:
        args["focus"] = focus
    if hops is not None:
        args["hops"] = hops
    reissue_args = {
        "root": str(root),
        "budget": token_budget,
        "bounded_output": True,
    }
    if focus is not None:
        reissue_args["focus"] = focus
    if hops is not None:
        reissue_args["hops"] = hops
    return {
        "repo": item["name"],
        "reason": "source_refs_omitted_to_bound_serialized_packet",
        "failure_code": "output_budget_exceeded",
        "total_source_refs": len(original_source_refs),
        "included_source_refs": len(included_source_refs),
        "omitted_source_refs": omitted,
        "source_refs_sha256": _sha(original_source_refs),
        "included_source_refs_sha256": _sha(included_source_refs),
        "approx_tokens": _approx_tokens(original_source_refs),
        "expand": {"tool": TOOL, "arguments": args},
        "reissue": {"tool": TOOL, "arguments": reissue_args},
        "provenance": {
            "source_ref_schema": "project-telos.source-ref/v1",
            "retained_repo_sha256": retained_repo_sha256,
        },
    }


def _minimal_bounded_overflow_receipt(
    envelope: dict,
    *,
    root: Path,
    focus: str | None,
    hops: int | None,
    token_budget: int,
) -> dict:
    pre_compaction = envelope["budget"]["pre_compaction_packet_approx_tokens"]
    omitted_names = [item["name"] for item in envelope.get("retained", [])]
    args = {"root": str(root), "budget": max(token_budget, pre_compaction),
            "bounded_output": False}
    if focus is not None:
        args["focus"] = focus
    if hops is not None:
        args["hops"] = hops
    preexisting_omitted = [dict(item) for item in envelope.get("omitted", [])]
    retained_omitted = [
        {
            "name": name,
            "reason": "bounded_output_minimal_receipt",
            "failure_code": "output_budget_exceeded",
            "approx_tokens": 0,
            "expand": {"tool": TOOL, "arguments": args},
        }
        for name in omitted_names
    ]
    omitted = _dedupe_omitted(preexisting_omitted + retained_omitted)
    omitted_failure_codes = sorted(
        {"budget_overflow", "output_budget_exceeded"}
        | {str(item.get("failure_code", "unknown")) for item in omitted}
    )
    return {
        "schema": SCHEMA,
        "tool": TOOL,
        "verification_verdict": "UNVERIFIABLE",
        "failure_codes": ["budget_overflow", "output_budget_exceeded"],
        "root": str(root),
        "focus": {"repo": focus, "hops": hops},
        "budget": {
            "token_budget": token_budget,
            "approx_tokens": 0,
            "bytes_per_token": BYTES_PER_TOKEN,
            "output_policy": "bounded_packet",
            "pre_compaction_packet_approx_tokens": pre_compaction,
        },
        "selection": {
            "mode": "focused" if focus else "workspace",
            "candidate_repos": envelope.get("selection", {}).get("candidate_repos", 0),
            "selected_repos": envelope.get("selection", {}).get("selected_repos", 0),
            "retained_repos": 0,
            "omitted_repos": len(omitted),
            "retained_names": [],
            "omitted_failure_codes": omitted_failure_codes,
        },
        "retained": [],
        "omitted": omitted,
        "source_ref_omissions": envelope.get("source_ref_omissions", []),
    }


def _refresh_selection(envelope: dict) -> None:
    retained = envelope.get("retained", [])
    omitted = envelope.get("omitted", [])
    envelope["selection"] = _selection(
        mode=envelope["selection"]["mode"],
        candidate_repo_count=envelope["selection"]["candidate_repos"],
        selected_repo_count=envelope["selection"]["selected_repos"],
        retained=retained,
        omitted=omitted,
    )
    codes = set(envelope["selection"].get("omitted_failure_codes", []))
    codes.update(item["failure_code"] for item in envelope.get("source_ref_omissions", []))
    envelope["selection"]["omitted_failure_codes"] = sorted(codes)


def _add_failure_code(envelope: dict, code: str) -> None:
    codes = envelope.setdefault("failure_codes", [])
    if code not in codes:
        codes.append(code)


def _set_packet_measurement(
    envelope: dict,
    *,
    transport: str = "canonical_json",
    mcp_response_id: object | None = None,
) -> None:
    budget = envelope["budget"]
    prior: tuple[int | None, int | None] = (None, None)
    for _ in range(8):
        serialized_bytes = _packet_bytes(
            envelope, transport=transport, mcp_response_id=mcp_response_id)
        approx = max(1, math.ceil(serialized_bytes / BYTES_PER_TOKEN))
        budget["packet_measurement"] = {
            "scope": _transport_scope(transport),
            "method": _transport_method(transport),
            "unit": "serialized_utf8_json_bytes_ceiling_div_4",
            "boundary": _transport_boundary(transport),
            "serialized_bytes": serialized_bytes,
        }
        budget["packet_approx_tokens"] = approx
        current = (serialized_bytes, approx)
        if current == prior:
            return
        prior = current


def _packet_bytes(
    envelope: dict,
    *,
    transport: str = "canonical_json",
    mcp_response_id: object | None = None,
) -> int:
    if transport == "canonical_json":
        text = json.dumps(envelope, sort_keys=True)
    elif transport == "cli_json_stdout":
        text = json.dumps(envelope, indent=2, sort_keys=True) + "\n"
    elif transport == "mcp_jsonrpc_tool_response":
        tool_text = json.dumps(envelope, indent=2, sort_keys=True)
        response = {
            "jsonrpc": "2.0",
            "id": mcp_response_id,
            "result": {
                "content": [{"type": "text", "text": tool_text}],
                "isError": False,
            },
        }
        text = json.dumps(response, sort_keys=True)
    else:
        raise ValueError(f"unknown bounded_output transport: {transport}")
    return len(text.encode("utf-8"))


def _transport_scope(transport: str) -> str:
    if transport == "canonical_json":
        return "entire_serialized_context_envelope"
    if transport == "cli_json_stdout":
        return "cli_json_stdout"
    if transport == "mcp_jsonrpc_tool_response":
        return "mcp_jsonrpc_tool_response"
    raise ValueError(f"unknown bounded_output transport: {transport}")


def _transport_method(transport: str) -> str:
    if transport == "canonical_json":
        return "json.dumps(sort_keys=True).encode('utf-8')"
    if transport == "cli_json_stdout":
        return (
            "json.dumps(indent=2, sort_keys=True) + LF newline, "
            "written as exact utf-8 bytes"
        )
    if transport == "mcp_jsonrpc_tool_response":
        return "json.dumps(JSON-RPC tool response, sort_keys=True).encode('utf-8')"
    raise ValueError(f"unknown bounded_output transport: {transport}")


def _transport_boundary(transport: str) -> str:
    if transport == "canonical_json":
        return (
            "Approximate serialized-byte budget for the canonical Python envelope JSON; "
            "not model-tokenizer output."
        )
    if transport == "cli_json_stdout":
        return (
            "Approximate serialized-byte budget for the emitted CLI --json stdout, "
            "including pretty JSON and trailing LF newline written as exact utf-8 bytes; "
            "not model-tokenizer output."
        )
    if transport == "mcp_jsonrpc_tool_response":
        return (
            "Approximate serialized-byte budget for the MCP JSON-RPC tool response wrapper; "
            "not model-tokenizer output."
        )
    raise ValueError(f"unknown bounded_output transport: {transport}")


def _packet_tokens(
    envelope: dict,
    *,
    ceiling: bool,
    transport: str = "canonical_json",
    mcp_response_id: object | None = None,
) -> int:
    raw = _packet_bytes(envelope, transport=transport, mcp_response_id=mcp_response_id)
    if ceiling:
        return max(1, math.ceil(raw / BYTES_PER_TOKEN))
    return max(1, raw // BYTES_PER_TOKEN)


def _ranked_repos(pack: dict, focus: str | None = None) -> list[dict]:
    sal = pack.get("salience", {})
    return sorted(
        pack.get("repos", []),
        key=lambda repo: (
            repo["name"] != focus,
            -sal.get(repo["name"], {}).get("in_degree", 0),
            -sal.get(repo["name"], {}).get("out_degree", 0),
            repo["name"],
        ),
    )


def _repo_item(repo: dict, pack: dict, source_refs: list[dict]) -> dict:
    sal = pack.get("salience", {}).get(repo["name"], {"in_degree": 0, "out_degree": 0})
    return {
        "name": repo["name"],
        "roles": pack.get("roles", {}).get(repo["name"], []),
        "ecosystems": repo.get("ecosystems", []),
        "description": repo.get("description", ""),
        "salience": {"in_degree": sal.get("in_degree", 0), "out_degree": sal.get("out_degree", 0)},
        "source_refs": source_refs,
    }


def _source_refs(graph: DependencyGraph, root: Path) -> dict[str, list[dict]]:
    repo_paths = {node.name: Path(node.path) for node in graph.repos}
    refs: dict[str, dict[tuple[str, int | None, str], dict]] = {
        node.name: {} for node in graph.repos
    }
    for edge in graph.edges:
        for signal in edge.signals:
            if signal.evidence_file and edge.from_repo in repo_paths:
                ref = _source_ref(
                    edge.from_repo,
                    repo_paths[edge.from_repo],
                    root,
                    signal.evidence_file,
                    signal.evidence_line,
                    signal.kind,
                )
                refs[edge.from_repo].setdefault(
                    (ref["path"], ref["line"], ref["kind"]), ref)
    for repo, path in repo_paths.items():
        if not refs[repo]:
            fallback = _repo_ref(repo, path, root)
            if fallback is not None:
                refs[repo][(fallback["path"], fallback["line"], fallback["kind"])] = fallback
    return {
        repo: sorted(values.values(), key=lambda ref: (ref["path"], ref["line"] or 0, ref["kind"]))
        for repo, values in refs.items()
    }


def _repo_ref(repo: str, repo_path: Path, root: Path) -> dict | None:
    for name in ("pyproject.toml", "package.json", "README.md", "README.rst", "README.txt"):
        if (repo_path / name).is_file():
            return _source_ref(repo, repo_path, root, name, None, "repo")
    return None


def _source_ref(
    repo: str,
    repo_path: Path,
    root: Path,
    evidence_file: str,
    line: int | None,
    kind: str,
) -> dict:
    abs_path = (repo_path / evidence_file).resolve()
    return {
        "schema": "project-telos.source-ref/v1",
        "repo": repo,
        "repo_path": _rel(repo_path.resolve(), root),
        "path": _rel(abs_path, root),
        "kind": kind,
        "line": line,
        "sha256": _file_sha(abs_path),
        "expand": {
            "tool": "gather.docs",
            "arguments": {
                "path": _rel(abs_path, root),
                "scope": TOOL,
            },
        },
    }


def _focus_omissions(source: DependencyGraph, focused: DependencyGraph) -> list[dict]:
    kept = {node.name for node in focused.repos}
    return [_omitted(node.name, "outside_focus_or_budget", 0)
            for node in source.repos if node.name not in kept]


def _omitted(name: str, reason: str, approx_tokens: int) -> dict:
    return {
        "name": name,
        "reason": reason,
        "failure_code": reason,
        "approx_tokens": approx_tokens,
    }


def _dedupe_omitted(items: list[dict]) -> list[dict]:
    out: dict[str, dict] = {}
    for item in items:
        out.setdefault(item["name"], item)
    return sorted(out.values(), key=lambda item: item["name"])


def _selection(
    *,
    mode: str,
    candidate_repo_count: int,
    selected_repo_count: int,
    retained: list[dict],
    omitted: list[dict],
) -> dict:
    return {
        "mode": mode,
        "candidate_repos": candidate_repo_count,
        "selected_repos": selected_repo_count,
        "retained_repos": len(retained),
        "omitted_repos": len(omitted),
        "retained_names": sorted(item["name"] for item in retained),
        "omitted_failure_codes": sorted({item["failure_code"] for item in omitted}),
    }


FRESHNESS_VERDICT_SCHEMA = "index.context-envelope-freshness-verdict/v1"


def verify_envelope_freshness(envelope: dict, graph: DependencyGraph) -> dict:
    """Re-derive an envelope's freshness against the current workspace and return a verdict.

    The envelope binds itself to a workspace fingerprint (a root hash plus a per-repo hash
    for every retained repo). This re-fingerprints the workspace from ``graph`` and confirms
    those hashes still hold, so a cached envelope that went stale (the workspace changed
    under it) is caught and the drifted repos are named -- the staleness failure mode of
    cached context, made a check instead of a hope. MATCH when nothing moved, else DRIFT.
    Re-derived from the workspace, never trusted from the envelope. Read-only."""
    fr = envelope.get("freshness") or {}
    repo_paths = {node.name: Path(node.path) for node in graph.repos}
    stamp = workspace_fingerprint(repo_paths)
    root_ok = stamp["root"] == fr.get("workspace_root_sha256")
    retained = fr.get("retained_repo_sha256") or {}
    drifted = sorted(n for n, sha in retained.items() if stamp["repos"].get(n) != sha)
    missing = sorted(n for n in retained if n not in stamp["repos"])
    fresh = root_ok and not drifted and not missing
    return {
        "schema": FRESHNESS_VERDICT_SCHEMA,
        "verdict": "MATCH" if fresh else "DRIFT",
        "fresh": fresh,
        "workspace_root_ok": root_ok,
        "drifted_repos": drifted,
        "missing_repos": missing,
        "expected_root_sha256": fr.get("workspace_root_sha256"),
        "actual_root_sha256": stamp["root"],
        "checked_repos": sorted(retained),
    }


def _freshness(source_graph: DependencyGraph, retained: list[dict]) -> dict:
    repo_paths = {node.name: Path(node.path) for node in source_graph.repos}
    stamp = workspace_fingerprint(repo_paths)
    retained_names = {item["name"] for item in retained}
    retained_repo_sha256 = {
        name: stamp["repos"][name]
        for name in sorted(retained_names)
        if name in stamp["repos"]
    }
    return {
        "schema": FRESHNESS_ENVELOPE_SCHEMA,
        "source_schema": FRESHNESS_SCHEMA,
        "workspace_root_sha256": stamp["root"],
        "repo_count": len(stamp["repos"]),
        "retained_repo_sha256": retained_repo_sha256,
        "recheck": {
            "tool": "index.freshness",
            "command": "index check --freshness; index freshness --cert CERT --root ROOT",
        },
    }


def _browser_evidence_refs(refs: list[dict]) -> list[dict]:
    allowed = ("ref", "schema", "mode", "hash", "verification", "side_effect")
    return [
        {key: ref[key] for key in allowed if key in ref}
        for ref in refs
        if isinstance(ref, dict)
    ]


def _base_tokens(pack: dict) -> int:
    return _approx_tokens({
        "schema": SCHEMA,
        "relations": len(pack.get("relations", [])),
        "cycles": pack.get("cycles", []),
        "warnings": pack.get("warnings", []),
    })


def _approx_tokens(value: object) -> int:
    return max(1, len(json.dumps(value, sort_keys=True, separators=(",", ":"))) // BYTES_PER_TOKEN)


def _sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
