"""Seal and verify the wiki artifact: page hashes, graph re-derivation, commit pin.

A page hash is the canonical SHA-256 of the page object (docs/PROTOCOL.md).
The verdict is one of three words, MATCH, DRIFT, or UNVERIFIABLE, never a
fourth, with exit codes 0/1/2 to match the existing verify contract. DRIFT
means a page was tampered with, the wiki claims a module edge the real graph
does not contain, or the repo moved off the pinned commit. UNVERIFIABLE means
the artifact cannot be evaluated at all. A verifier that cannot fail on a
known-bad input is not a verifier; the negative fixtures live in the tests.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..certify.certificate import canonical_sha

WIKI_SCHEMA = "index.wiki/1"
VERIFICATION_SCHEMA = "index.wiki-verification/1"
VERDICT_EXIT = {"MATCH": 0, "DRIFT": 1, "UNVERIFIABLE": 2}

# The data island the HTML artifact embeds; render and extract share one truth.
EMBED_OPEN = '<script id="wiki-data" type="application/json">'
EMBED_CLOSE = "</script>"


def head_commit(root: Path | str) -> str:
    """Full HEAD sha of the repo at root, or "unversioned" for a non-git root."""
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "unversioned"
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else "unversioned"


def build_manifest(pages: list[dict], *, repo: str, commit: str,
                   inputs: dict, tool_version: str) -> dict:
    return {
        "schema": WIKI_SCHEMA,
        "repo": repo,
        "commit": commit,
        "tool_version": tool_version,
        "pages": [{"id": p["id"], "sha256": canonical_sha(p)} for p in pages],
        "inputs": inputs,
    }


def claimed_module_edges(pages: list[dict]) -> set[tuple[str, str]]:
    """Every module-level edge the wiki asserts, from module and package pages."""
    edges: set[tuple[str, str]] = set()
    for page in pages:
        if page.get("kind") == "module":
            for imp in page.get("imports", []):
                edges.add((page.get("module", ""), imp.get("to", "")))
            for dep in page.get("dependents", []):
                edges.add((dep.get("from", ""), page.get("module", "")))
        elif page.get("kind") == "package":
            for group in list(page.get("imports", [])) + list(page.get("dependents", [])):
                for via in group.get("via", []):
                    edges.add((via.get("from", ""), via.get("to", "")))
    return edges


def claimed_symbol_calls(pages: list[dict]) -> set[tuple[str, str]]:
    """Every resolved symbol-call edge (caller, callee) the wiki asserts, drawn
    from the callers/callees of each symbol page. An unresolved reference (which
    the pages surface separately, without a to_symbol) is never a claimed edge."""
    edges: set[tuple[str, str]] = set()
    for page in pages:
        if page.get("kind") != "symbol":
            continue
        sym = page.get("symbol", "")
        for callee in page.get("callees", []):
            edges.add((sym, callee.get("to_symbol", "")))
        for caller in page.get("callers", []):
            edges.add((caller.get("from_symbol", ""), sym))
    return edges


def _structural_gap(artifact: object) -> str | None:
    if not isinstance(artifact, dict):
        return "artifact is not a JSON object"
    if artifact.get("schema") != WIKI_SCHEMA:
        return f"artifact schema must be {WIKI_SCHEMA}"
    pages, manifest = artifact.get("pages"), artifact.get("manifest")
    if not isinstance(pages, list) or not pages:
        return "artifact carries no pages"
    if any(not isinstance(p, dict) or "id" not in p for p in pages):
        return "artifact carries a page without an id"
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pages"), list):
        return "artifact carries no sealing manifest"
    return None


def _hash_findings(artifact: dict) -> list[dict]:
    listed = {e.get("id"): e.get("sha256")
              for e in artifact["manifest"]["pages"] if isinstance(e, dict)}
    findings: list[dict] = []
    seen: set = set()
    for page in artifact["pages"]:
        pid = page["id"]
        seen.add(pid)
        if pid not in listed:
            findings.append({"rule": "page-unlisted",
                             "detail": f"page {pid!r} is not sealed by the manifest"})
        elif canonical_sha(page) != listed[pid]:
            findings.append({"rule": "page-tampered",
                             "detail": f"page {pid!r} does not match its sealed hash"})
    for pid in sorted(set(listed) - seen, key=str):
        findings.append({"rule": "page-missing",
                         "detail": f"manifest seals page {pid!r} "
                                   "but the artifact does not carry it"})
    return findings


def _report(verdict: str, findings: list[dict], *, pages_checked: int,
            edges_checked: int, recheck: str) -> dict:
    return {"schema": VERIFICATION_SCHEMA, "verdict": verdict, "findings": findings,
            "pages_checked": pages_checked, "edges_checked": edges_checked,
            "recheck": recheck}


def verify_wiki(artifact: object, root: Path | str, *, recheck: str = "") -> dict:
    """Recompute page hashes and the graph derivation against the current tree."""
    root = Path(root)
    recheck = recheck or f'index wiki --verify <artifact> --root "{root}"'
    gap = _structural_gap(artifact)
    if gap is None and not root.is_dir():
        gap = f"root not found: {root}"
    if gap:
        return _report("UNVERIFIABLE", [{"rule": "artifact", "detail": gap}],
                       pages_checked=0, edges_checked=0, recheck=recheck)
    findings = _hash_findings(artifact)
    from ..internals import build_internals
    real = {(e.from_id, e.to_id) for e in build_internals(root).edges}
    claimed = claimed_module_edges(artifact["pages"])
    for frm, to in sorted(claimed - real):
        findings.append({"rule": "edge-not-in-graph",
                         "detail": f"wiki claims module edge {frm} -> {to} but the "
                                   "graph derived from the current tree does not contain it"})
    from ..symbols import build_symbol_graph, symbol_graph_to_claims
    real_symbol = symbol_graph_to_claims(build_symbol_graph(root))
    claimed_symbol = claimed_symbol_calls(artifact["pages"])
    for frm, to in sorted(claimed_symbol - real_symbol):
        findings.append({"rule": "symbol-call-not-in-graph",
                         "detail": f"wiki claims symbol call {frm} -> {to} but the "
                                   "symbol graph derived from the current tree does "
                                   "not contain it"})
    pinned, current = artifact["manifest"].get("commit"), head_commit(root)
    if pinned != current:
        findings.append({"rule": "commit-moved",
                         "detail": f"wiki is pinned to {pinned} "
                                   f"but the current tree is at {current}"})
    else:
        # Several pages assert content that no structured edge/hash check
        # re-derives once the manifest is resealed: the architecture DIAGRAM
        # (rendered svg/mermaid strings), the OVERVIEW facts (coverage, counts,
        # entry points), and the DOCS prose (sealed but never re-read from
        # source). Re-derive the whole pack from the tree (deterministic) and
        # confirm each such page is exactly its fresh re-render. Only compared
        # at the pinned commit, so a moved tree is named by commit-moved, not
        # double-counted here.
        from .pack import build_wiki_pack
        fresh = {p.get("kind"): p for p in build_wiki_pack(root)["pages"]}
        _CHECKS = (("architecture", "architecture-diagram-drift",
                    "the architecture diagram depicts structure the code does not have"),
                   ("overview", "overview-not-in-graph",
                    "the overview asserts facts the graph derived from the tree does not have"),
                   ("docs", "docs-not-in-source",
                    "a docs page asserts prose not re-derivable from the source markdown"))
        for kind, rule, detail in _CHECKS:
            stored = next((p for p in artifact["pages"]
                           if p.get("kind") == kind), None)
            fresh_page = fresh.get(kind)
            if stored is not None and fresh_page is not None and stored != fresh_page:
                findings.append({"rule": rule, "detail": detail})
    return _report("MATCH" if not findings else "DRIFT", findings,
                   pages_checked=len(artifact["pages"]),
                   edges_checked=len(claimed) + len(claimed_symbol), recheck=recheck)


def extract_embedded_pack(html_text: str) -> dict:
    """Pull the sealed pack back out of a rendered HTML artifact."""
    start = html_text.find(EMBED_OPEN)
    if start < 0:
        raise ValueError("no embedded wiki-data island found")
    start += len(EMBED_OPEN)
    end = html_text.find(EMBED_CLOSE, start)
    if end < 0:
        raise ValueError("embedded wiki-data island is unterminated")
    return json.loads(html_text[start:end])


def load_artifact(path: Path | str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("<"):
        return extract_embedded_pack(text)
    return json.loads(text)


def run_verify(artifact_path: Path | str, root: Path | str) -> dict:
    """The shared CLI/MCP verification payload; an unreadable artifact is UNVERIFIABLE."""
    recheck = f'index wiki --verify "{artifact_path}" --root "{root}"'
    try:
        artifact = load_artifact(artifact_path)
    except (OSError, ValueError) as exc:
        return _report("UNVERIFIABLE",
                       [{"rule": "artifact", "detail": f"cannot read artifact: {exc}"}],
                       pages_checked=0, edges_checked=0, recheck=recheck)
    return verify_wiki(artifact, root, recheck=recheck)
