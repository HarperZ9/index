"""Assemble repos (index) + docs into the two-layer atlas pack."""
from __future__ import annotations

import re
from pathlib import Path

from ..context.pack import to_json
from ..graph.build import DependencyGraph
from .docs import Doc, _norm          # reuse the SAME normalizer that built link_targets

_EDGE_SORT = lambda e: (e["from"], e["type"], e["to_kind"], e["to"])
_TOKEN = re.compile(r"[0-9a-z]+")


def _target_index(repo_names, docs):
    """normalized name -> (to_kind, id); repos win over docs on collision; first doc wins.

    Uses `_norm` (space/underscore -> dash, lowercased), the SAME normalization
    docs.py applied to `[[link]]` targets, so multi-word links like [[Auth Design]]
    resolve to a doc titled "Auth Design"."""
    idx: dict[str, tuple[str, str]] = {}
    for r in sorted(repo_names):
        idx.setdefault(_norm(r), ("repo", r))
    for d in docs:
        for cand in (d.title, Path(d.rel_path).stem):
            idx.setdefault(_norm(cand), ("doc", d.rel_path))
    return idx


def _describes(doc: Doc, repo_dirs: dict[str, str]) -> str | None:
    """The most-specific repo whose dir contains the doc's dir (by location), else None.

    A repo dir "" (repo at the workspace root) matches only a root-level doc
    (dir_rel == ""), never docs in subdirs, since the prefix branch requires
    a non-empty rdir."""
    best, best_len = None, -1
    for repo, rdir in repo_dirs.items():
        if doc.dir_rel == rdir or (rdir != "" and doc.dir_rel.startswith(rdir + "/")):
            if len(rdir) > best_len:
                best, best_len = repo, len(rdir)
    return best


def _mentions_name(body: str, name: str) -> bool:
    # case-insensitive whole-token match; treat '-'/'_' and spaces as separators
    pattern = r"(?<![0-9a-z])" + re.escape(name.lower()) + r"(?![0-9a-z])"
    return re.search(pattern, body.lower()) is not None


def _mention_tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(text.lower()))


def _doc_rows(docs: list[Doc]) -> list[dict]:
    return [{"id": d.rel_path, "title": d.title, "dir": d.dir_rel} for d in docs]


def _describes_edges(docs: list[Doc], repo_dirs: dict[str, str]) -> list[dict]:
    edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for d in docs:
        repo = _describes(d, repo_dirs)
        if repo is None:
            continue
        key = (d.rel_path, "repo", repo)
        if key not in seen:
            seen.add(key)
            edges.append({
                "type": "describes",
                "from": d.rel_path,
                "to": repo,
                "to_kind": "repo",
            })
    return sorted(edges, key=_EDGE_SORT)


def build_router_pack(graph: DependencyGraph, docs: list[Doc],
                      repo_dirs: dict[str, str]) -> dict:
    pack = to_json(graph)
    pack["docs"] = _doc_rows(docs)
    pack["knowledge_edges"] = _describes_edges(docs, repo_dirs)
    pack["knowledge_warnings"] = []
    pack["repo_dirs"] = dict(repo_dirs)
    return pack


def build_atlas_pack(graph: DependencyGraph, docs: list[Doc],
                     repo_dirs: dict[str, str]) -> dict:
    pack = to_json(graph)
    repo_names = {n["name"] for n in pack["repos"]}
    idx = _target_index(repo_names, docs)

    pack["docs"] = _doc_rows(docs)
    edges: list[dict] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, str]] = set()      # (from, to_kind, to), strongest wins

    def add(etype: str, frm: str, to_kind: str, to: str) -> None:
        key = (frm, to_kind, to)
        if to is None or key in seen:
            return
        seen.add(key)
        edges.append({"type": etype, "from": frm, "to": to, "to_kind": to_kind})

    # describes (by location): strongest
    for edge in _describes_edges(docs, repo_dirs):
        add("describes", edge["from"], edge["to_kind"], edge["to"])
    # links-to (from [[wiki-links]])
    for d in docs:
        for t in d.link_targets:
            hit = idx.get(t)
            if hit is None:
                warnings.append(f"{d.rel_path}: unresolved [[{t}]]")
                continue
            to_kind, to = hit
            if to_kind == "doc" and to == d.rel_path:
                continue                         # self-link
            add("links-to", d.rel_path, to_kind, to)

    # mentions (prose name-drops): weakest; deduped via `seen` against describes/links-to
    name_of = {("repo", r): r for r in repo_names}
    name_of.update({("doc", d.rel_path): d.title for d in docs})
    mention_targets = [
        (target, display, _mention_tokens(display))
        for target, display in sorted(name_of.items())
    ]
    for d in docs:
        body_tokens = _mention_tokens(d.body)
        for (to_kind, to), display, display_tokens in mention_targets:
            if (d.rel_path, to_kind, to) in seen:      # already a stronger edge
                continue
            if to_kind == "doc" and to == d.rel_path:
                continue
            if display_tokens and not display_tokens.issubset(body_tokens):
                continue
            if _mentions_name(d.body, display):       # display = repo name or doc title
                add("mentions", d.rel_path, to_kind, to)

    pack["knowledge_edges"] = sorted(edges, key=_EDGE_SORT)
    pack["knowledge_warnings"] = warnings
    return pack
