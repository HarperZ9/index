"""Budgeted context envelopes for large-codebase agent work."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..freshness import SCHEMA as FRESHNESS_SCHEMA, workspace_fingerprint
from ..graph.build import DependencyGraph
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
) -> dict:
    """Return a deterministic, receipt-backed context packet within ``token_budget``."""
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    source_graph = graph
    preserved = None
    candidate_repo_count = len(source_graph.repos)
    if focus:
        names = {node.name for node in graph.repos}
        if focus not in names:
            raise ValueError(f"unknown focus repo: {focus}")
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
    verdict = "UNVERIFIABLE" if failure_codes else "MATCH"
    fresh = _freshness(source_graph, retained)
    return {
        "schema": SCHEMA,
        "tool": TOOL,
        "verification_verdict": verdict,
        "failure_codes": failure_codes,
        "root": str(Path(root)),
        "focus": {"repo": focus, "hops": hops},
        "budget": {
            "token_budget": token_budget,
            "approx_tokens": min(approx_tokens, token_budget),
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
