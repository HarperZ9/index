"""The index workbench: every capability index derives, composed into ONE
self-contained page.

Separately, index already ships a verified wiki, an interactive atlas, a
context lens, freshness fingerprints, and a symbol/dependency graph — each its
own artifact. The workbench folds the single-pass surfaces into one pack a
single HTML shell renders: a map you navigate, the docs that describe it, the
context lens over its token budget, and a health panel with the freshness
fingerprint, cycles, and salience audit. Every dependency edge carries its
file:line evidence; nothing is authored, everything re-derives.

Honest scope (stated on the page, not hidden): freshness/drift VERDICTS need a
prior pinned snapshot to diff against. A single `--root` pass cannot emit a
drift verdict, so the workbench shows the current fingerprint (the baseline a
later `index drift` compares to) and the structural health that IS computable
in one pass — never a fabricated FRESH/STALE badge.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .context.lens import build_lens_pack
from .freshness.fingerprint import workspace_fingerprint
from .graph.build import DependencyGraph
from .knowledge.atlas import build_atlas_pack
from .knowledge.markdown import render_markdown
from .viz.atlas_html import _backlinks
from .viz.atlas_layout import build_atlas_layout
from .viz.atlas_svg import render_atlas_svg

SCHEMA = "project-telos.workbench/v1"
TOOL = "index.workbench"
ACTION_SCHEMA = "project-telos.flagship-action/v1"


def load_spine(spine_dir: str | Path | None, root: Path) -> dict:
    """Ingest captured flagship-action envelopes (the peers' own doctor/status
    output) and detect on-disk peer surfaces. FAIL CLOSED: a file that is not a
    valid flagship-action envelope is skipped WITH ITS REASON recorded, never
    guessed at. Peers stay peers: the forum ledger is reported as present with
    the forum command to inspect it — index never parses a peer's internals."""
    tools: list[dict] = []
    skipped: list[dict] = []
    ring: list[dict] = []
    if spine_dir is not None:
        for p in sorted(Path(spine_dir).glob("*.json")):
            try:
                env = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                skipped.append({"file": p.name, "reason": f"unreadable: {exc}"})
                continue
            if env.get("schema") != ACTION_SCHEMA or "tool" not in env:
                skipped.append({"file": p.name,
                                "reason": f"not a {ACTION_SCHEMA} envelope"})
                continue
            checks = (env.get("native") or {}).get("checks", [])
            tools.append({
                "tool": env["tool"], "version": env.get("tool_version", ""),
                "command": env.get("command", ""), "status": env.get("status", ""),
                "checks": [{"name": c.get("name", ""), "status": c.get("status", "")}
                           for c in checks],
                "source_file": p.name,
            })
            for na in env.get("next_actions", []):
                ring.append({"from": env["tool"], "to": na.get("tool", ""),
                             "action": na.get("action", ""),
                             "reason": na.get("reason", "")})
    ledger = root / ".telos" / "forum-ledger"
    surfaces = []
    if ledger.is_dir():
        surfaces.append({
            "peer": "forum", "surface": "causal ledger",
            "path": str(ledger), "entries": sum(1 for _ in ledger.iterdir()),
            "inspect": "forum ledger summary  (or MCP forum.ledger.summary)"})
    return {"tools": sorted(tools, key=lambda t: t["tool"]),
            "ring": sorted(ring, key=lambda e: (e["from"], e["to"])),
            "skipped": skipped, "peer_surfaces": surfaces,
            "capture": ("each flagship's doctor/status --json IS the envelope; "
                        "drop them in a directory and pass --spine-dir")}


def _evidence(rel: dict) -> list[dict]:
    """The file:line signals behind a dependency edge — the 'why' of the map."""
    out = []
    for s in rel.get("signals", []):
        if s.get("file"):
            out.append({"kind": s.get("kind", ""), "file": s["file"], "line": s.get("line")})
    return out


def _repo_view(pack: dict, fresh: dict) -> list[dict]:
    sal = pack.get("salience", {})
    roles = pack.get("roles", {})
    fresh_repos = fresh.get("repos", {})
    describes: dict[str, list[str]] = {}
    for e in pack.get("knowledge_edges", []):
        if e["type"] == "describes" and e["to_kind"] == "repo":
            describes.setdefault(e["to"], []).append(e["from"])
    deps: dict[str, list[dict]] = {}
    for r in pack.get("relations", []):
        if r.get("external"):
            continue
        deps.setdefault(r["from"], []).append({
            "to": r["to"], "confidence": r.get("confidence", ""),
            "in_cycle": r.get("in_cycle", False), "evidence": _evidence(r)})
    out = []
    for repo in pack.get("repos", []):
        name = repo["name"]
        s = sal.get(name, {})
        out.append({
            "name": name,
            "roles": roles.get(name, []),
            "ecosystems": repo.get("ecosystems", []),
            "description": repo.get("description", ""),
            "markers": repo.get("markers", []),
            "in_degree": s.get("in_degree", 0),
            "out_degree": s.get("out_degree", 0),
            "depends_on": sorted(deps.get(name, []), key=lambda d: d["to"]),
            "documented_by": sorted(describes.get(name, [])),
            "fingerprint": fresh_repos.get(name, ""),
        })
    return sorted(out, key=lambda r: r["name"])


def _summary(pack: dict, repos: list[dict]) -> dict:
    role_counts: dict[str, int] = {}
    for r in repos:
        for role in (r["roles"] or ["untyped"]):
            role_counts[role] = role_counts.get(role, 0) + 1
    edge_types: dict[str, int] = {}
    for e in pack.get("knowledge_edges", []):
        edge_types[e["type"]] = edge_types.get(e["type"], 0) + 1
    return {
        "repos": len(repos),
        "docs": len(pack.get("docs", [])),
        "relations": len([r for r in pack.get("relations", []) if not r.get("external")]),
        "knowledge_edges": len(pack.get("knowledge_edges", [])),
        "cycles": len(pack.get("cycles", [])),
        "warnings": len(pack.get("warnings", [])) + len(pack.get("knowledge_warnings", [])),
        "role_counts": dict(sorted(role_counts.items())),
        "edge_types": dict(sorted(edge_types.items())),
        "top_salience": [r["name"] for r in sorted(
            repos, key=lambda r: (-r["in_degree"], -r["out_degree"], r["name"]))[:8]],
    }


def build_workbench_pack(
    graph: DependencyGraph,
    docs: list,
    repo_dirs: dict[str, str],
    *,
    root: Path | str,
    token_budget: int = 6000,
    spine_dir: str | Path | None = None,
) -> dict:
    """Compose the atlas, docs, freshness fingerprint, lens, and health into one
    deterministic, self-contained pack. The SVG (map markup) rides along under
    'svg'; everything else is JSON the shell renders and the receipt seals."""
    pack = build_atlas_pack(graph, docs, repo_dirs)
    pack["doc_html"] = {d.rel_path: render_markdown(d.body)
                        for d in sorted(docs, key=lambda d: d.rel_path)}
    pack["backlinks"] = _backlinks(pack)
    svg = render_atlas_svg(build_atlas_layout(pack))
    fresh = workspace_fingerprint({n.name: Path(n.path) for n in graph.repos})
    repos = _repo_view(pack, fresh)
    lens = build_lens_pack(graph, root=root, token_budget=token_budget)
    wb = {
        "schema": SCHEMA,
        "tool": TOOL,
        "root": str(root),
        "summary": _summary(pack, repos),
        "repos": repos,
        "docs": sorted(pack.get("docs", []), key=lambda d: d["id"]),
        "doc_html": pack["doc_html"],
        "knowledge_edges": pack.get("knowledge_edges", []),
        "backlinks": pack["backlinks"],
        "cycles": [list(c) for c in pack.get("cycles", [])],
        "warnings": list(pack.get("warnings", [])),
        "knowledge_warnings": list(pack.get("knowledge_warnings", [])),
        "salience_audit": pack.get("salience_audit", []),
        "freshness": {
            "schema": fresh.get("schema", ""),
            "root_sha256": fresh.get("root", ""),
            "repos": fresh.get("repos", {}),
            "note": ("current fingerprint only; a FRESH/STALE drift verdict "
                     "requires a prior snapshot"),
            "recheck": "index freshness --cert CERT --root ROOT; index drift --from-snap A --to-snap B",
        },
        "lens": {
            "verdict": lens["envelope"]["verification_verdict"],
            "budget": lens["envelope"]["budget"],
            "replay": lens["replay"],
        },
        "spine": load_spine(spine_dir, Path(root)),
    }
    wb["receipt_sha256"] = _sha(wb)
    wb["svg"] = svg                       # markup, added after sealing the data
    return wb


def _sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
