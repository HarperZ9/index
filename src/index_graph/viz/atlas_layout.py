"""Two-layer atlas layout: repo positions (reused) + doc satellites + knowledge band."""
from __future__ import annotations

from dataclasses import dataclass

from .layout import build_layout, LayoutModel, MARGIN

_DOC_W, _DOC_H, _ROW_GAP, _COL_GAP = 160.0, 30.0, 10.0, 24.0


@dataclass(frozen=True)
class DocNode:
    id: str
    title: str
    x: float
    y: float
    w: float
    h: float
    describes: str | None          # repo name, or None for a band (cross-cutting) doc


@dataclass(frozen=True)
class KEdge:
    type: str                      # describes | links-to | mentions
    frm: str
    to: str
    to_kind: str                   # repo | doc
    points: tuple[tuple[float, float], tuple[float, float]]


@dataclass(frozen=True)
class AtlasLayout:
    repo_layout: LayoutModel
    docs: tuple[DocNode, ...]
    kedges: tuple[KEdge, ...]
    width: float
    height: float


def build_atlas_layout(pack: dict, *, include_external: bool = True) -> AtlasLayout:
    repo_layout = build_layout(pack, include_external=include_external)
    repo_by_name = {n.name: n for n in repo_layout.nodes}

    # describes target per doc (first by sorted edge order wins -> deterministic)
    describes: dict[str, str] = {}
    for e in sorted(pack.get("knowledge_edges", []), key=lambda e: (e["from"], e["type"], e["to_kind"], e["to"])):
        if e["type"] == "describes" and e["from"] not in describes:
            describes[e["from"]] = e["to"]

    docs_meta = sorted(pack.get("docs", []), key=lambda d: d["id"])
    region_top = repo_layout.height + 50.0
    placed: dict[str, DocNode] = {}

    # described docs -> one column per repo, columns flow left-to-right without overlapping
    by_repo: dict[str, list[dict]] = {}
    for d in docs_meta:
        target = describes.get(d["id"])
        if target in repo_by_name:
            by_repo.setdefault(target, []).append(d)
    cursor_x = MARGIN
    col_depth = 0
    for repo in sorted(by_repo, key=lambda r: (repo_by_name[r].x, r)):
        x = max(repo_by_name[repo].x, cursor_x)        # under its repo, never overlapping the prior column
        for k, d in enumerate(by_repo[repo]):
            y = region_top + k * (_DOC_H + _ROW_GAP)
            placed[d["id"]] = DocNode(d["id"], d["title"], x, y, _DOC_W, _DOC_H, repo)
        cursor_x = x + _DOC_W + _COL_GAP
        col_depth = max(col_depth, len(by_repo[repo]))

    # band docs (describe nothing / unknown repo) -> a wrapping row beneath the columns
    band_top = region_top + max(col_depth, 1) * (_DOC_H + _ROW_GAP) + 40.0
    width_guess = max(repo_layout.width, cursor_x)
    bx = MARGIN
    for d in docs_meta:
        if d["id"] in placed:
            continue
        if bx > MARGIN and bx + _DOC_W + MARGIN > width_guess:
            bx = MARGIN
            band_top += _DOC_H + _ROW_GAP
        placed[d["id"]] = DocNode(d["id"], d["title"], bx, band_top, _DOC_W, _DOC_H, None)
        bx += _DOC_W + _COL_GAP

    docs = tuple(placed[d["id"]] for d in docs_meta)

    def _center(node_id: str, kind: str):
        if kind == "repo" and node_id in repo_by_name:
            r = repo_by_name[node_id]
            return (r.x + r.w / 2.0, r.y + r.h / 2.0)
        if node_id in placed:
            d = placed[node_id]
            return (d.x + d.w / 2.0, d.y + d.h / 2.0)
        return None

    kedges: list[KEdge] = []
    for e in sorted(pack.get("knowledge_edges", []), key=lambda e: (e["from"], e["type"], e["to_kind"], e["to"])):
        a = _center(e["from"], "doc")
        b = _center(e["to"], e["to_kind"])
        if a is not None and b is not None:
            kedges.append(KEdge(e["type"], e["from"], e["to"], e["to_kind"], (a, b)))

    width = max([d.x + d.w for d in docs] + [repo_layout.width]) + MARGIN
    height = max([d.y + d.h for d in docs] + [repo_layout.height]) + MARGIN
    return AtlasLayout(repo_layout, docs, tuple(kedges), width, height)
