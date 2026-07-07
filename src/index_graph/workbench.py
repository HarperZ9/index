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
from .viz.atlas_layout import build_atlas_layout
from .viz.atlas_svg import render_atlas_svg

SCHEMA = "project-telos.workbench/v1"
TOOL = "index.workbench"
ACTION_SCHEMA = "project-telos.flagship-action/v1"

# Page-weight budgets. Large workspaces (2k+ docs) produced a 60MB page that
# choked renderers — a robustness failure. Budgets are HONEST: what is dropped
# is counted and shown on the page ("N of M"), search metadata stays complete,
# and every cap is overridable at the CLI. Never a silent truncation.
MAX_DOC_BODIES = 200          # rendered markdown bodies embedded in the page
MAX_MAP_DOCS_PER_REPO = 6     # doc satellites drawn under one repo on the map
MAX_MAP_BAND_DOCS = 40        # cross-cutting (band) docs drawn on the map
MAX_MENTIONS = 2000           # weakest-tier edges embedded (describes/links-to
                              # always ship in full; mention drops are counted)


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


def _rank_docs(pack: dict) -> list[str]:
    """Doc ids by connectivity (strongest knowledge edges first), then id.
    Deterministic; drives which bodies are embedded and which nodes are drawn."""
    weight = {"describes": 3, "links-to": 2, "mentions": 1}
    score: dict[str, int] = {d["id"]: 0 for d in pack.get("docs", [])}
    for e in pack.get("knowledge_edges", []):
        w = weight.get(e["type"], 0)
        if e["from"] in score:
            score[e["from"]] += w
        if e.get("to_kind") == "doc" and e["to"] in score:
            score[e["to"]] += w
    return sorted(score, key=lambda i: (-score[i], i))


def _map_pack(pack: dict, ranked: list[str]) -> dict:
    """A copy of the pack with docs capped for the MAP ONLY (satellites per
    repo + band docs), so the SVG stays renderable on huge workspaces. The
    full doc list remains in the workbench data for search and the Docs view."""
    describes: dict[str, str] = {}
    for e in sorted(pack.get("knowledge_edges", []),
                    key=lambda e: (e["from"], e["type"], e["to_kind"], e["to"])):
        if e["type"] == "describes" and e["from"] not in describes:
            describes[e["from"]] = e["to"]
    rank = {rid: i for i, rid in enumerate(ranked)}
    per_repo: dict[str, int] = {}
    band = 0
    keep: set[str] = set()
    for d in sorted(pack.get("docs", []), key=lambda d: rank.get(d["id"], 1 << 30)):
        target = describes.get(d["id"])
        if target is not None:
            if per_repo.get(target, 0) < MAX_MAP_DOCS_PER_REPO:
                per_repo[target] = per_repo.get(target, 0) + 1
                keep.add(d["id"])
        elif band < MAX_MAP_BAND_DOCS:
            band += 1
            keep.add(d["id"])
    capped = dict(pack)
    capped["docs"] = [d for d in pack.get("docs", []) if d["id"] in keep]
    capped["knowledge_edges"] = [
        e for e in pack.get("knowledge_edges", [])
        if e["type"] != "mentions"
        and e["from"] in keep and (e.get("to_kind") != "doc" or e["to"] in keep)]
    return capped


def build_workbench_pack(
    graph: DependencyGraph,
    docs: list,
    repo_dirs: dict[str, str],
    *,
    root: Path | str,
    token_budget: int = 6000,
    spine_dir: str | Path | None = None,
    max_doc_bodies: int = MAX_DOC_BODIES,
) -> dict:
    """Compose the atlas, docs, freshness fingerprint, lens, and health into one
    deterministic, self-contained pack. The SVG (map markup) rides along under
    'svg'; everything else is JSON the shell renders and the receipt seals.
    Page-weight budgets (MAX_*) keep huge workspaces renderable; every drop is
    counted in `summary`/`doc_meta` and stated on the page."""
    pack = build_atlas_pack(graph, docs, repo_dirs)
    ranked_docs = _rank_docs(pack)
    structural = [e for e in pack.get("knowledge_edges", [])
                  if e["type"] != "mentions"]
    mentions = [e for e in pack.get("knowledge_edges", [])
                if e["type"] == "mentions"]
    kept_mentions = sorted(mentions, key=lambda e: (e["from"], e["to"]))[:MAX_MENTIONS]
    pack["knowledge_edges"] = structural + kept_mentions
    embed = set(ranked_docs[:max_doc_bodies])
    body_of = {d.rel_path: d.body for d in docs}
    pack["doc_html"] = {rid: render_markdown(body_of[rid])
                        for rid in sorted(embed) if rid in body_of}
    map_capped = _map_pack(pack, ranked_docs)
    svg = render_atlas_svg(build_atlas_layout(map_capped))
    fresh = workspace_fingerprint({n.name: Path(n.path) for n in graph.repos})
    repos = _repo_view(pack, fresh)
    lens = build_lens_pack(graph, root=root, token_budget=token_budget)
    lens_order = [{k: o[k] for k in ("name", "cost", "roles", "salience")}
                  for o in lens["replay"]["order"]]   # page never reads source_refs
    wb = {
        "schema": SCHEMA,
        "tool": TOOL,
        "root": str(root),
        "summary": _summary(pack, repos),
        "repos": repos,
        "docs": sorted(pack.get("docs", []), key=lambda d: d["id"]),
        "doc_html": pack["doc_html"],
        "knowledge_edges": pack.get("knowledge_edges", []),
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
            "replay": {"rule": lens["replay"]["rule"],
                       "base_tokens": lens["replay"]["base_tokens"],
                       "order": lens_order},
        },
        "doc_meta": {
            "total": len(pack.get("docs", [])),
            "bodies_embedded": len(pack["doc_html"]),
            "map_docs": len(map_capped["docs"]),
            "mentions_total": len(mentions),
            "mentions_embedded": len(kept_mentions),
            "bodies_note": ("bodies beyond the budget are not embedded; the doc "
                            "list and search stay complete — open the file at "
                            "its id path, or raise --max-doc-bodies"),
        },
        "spine": load_spine(spine_dir, Path(root)),
    }
    wb["receipt_sha256"] = _sha(wb)
    wb["svg"] = svg                       # markup, added after sealing the data
    return wb


def _sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
