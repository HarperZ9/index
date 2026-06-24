"""Render an AtlasLayout to a self-contained two-layer SVG (repos + docs)."""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from .atlas_layout import AtlasLayout, DocNode, KEdge
from .svg import _node_svg, _edge_svg          # reuse repo node + dependency edge renderers
from .theme import THEME, svg_style


def _atlas_style() -> str:
    t = THEME
    return (
        f".docnode rect{{fill:{t.bg};stroke:{t.gold};stroke-dasharray:3 2;}}"
        f".docnode text{{font-family:{t.font_mono};fill:{t.ink};font-size:11px;}}"
        f".docnode.band rect{{stroke:{t.teal};}}"
        f".docnode.sel rect{{stroke:{t.accent};stroke-width:2;stroke-dasharray:none;}}"
        f".kedge{{fill:none;stroke-width:1;}}"
        f".kedge-describes{{stroke:{t.gold};}}"
        f".kedge-links-to{{stroke:{t.ok};stroke-dasharray:4 3;}}"
        f".kedge-mentions{{stroke:{t.muted};stroke-dasharray:1 4;opacity:.35;}}"
        f".kedge.dim,.node.dim,.docnode.dim,.edge.dim{{opacity:.08;}}"
    )


def _doc_svg(d: DocNode) -> str:
    cls = "docnode" + ("" if d.describes is not None else " band")
    return (
        f"<g class={quoteattr(cls)} data-doc={quoteattr(d.id)} data-title={quoteattr(d.title)} "
        f'tabindex="0" role="img" aria-label={quoteattr(d.title + " (doc)")}>'
        f'<rect x="{d.x:.2f}" y="{d.y:.2f}" width="{d.w:.2f}" height="{d.h:.2f}" rx="3"/>'
        f'<text x="{d.x + 8:.2f}" y="{d.y + d.h / 2 + 4:.2f}">{escape(d.title)}</text></g>'
    )


def _kedge_svg(k: KEdge) -> str:
    (a, b) = k.points
    cls = "kedge kedge-" + k.type
    return (
        f"<line class={quoteattr(cls)} data-ktype={quoteattr(k.type)} "
        f"data-from={quoteattr(k.frm)} data-to={quoteattr(k.to)} "
        f'x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}"/>'
    )


def render_atlas_svg(atlas: AtlasLayout) -> str:
    rl = atlas.repo_layout
    defs = (
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{THEME.muted}"/></marker></defs>'
    )
    style = f"<style>{svg_style()}{_atlas_style()}</style>"
    kedges = "".join(_kedge_svg(k) for k in atlas.kedges)
    repo_edges = "".join(_edge_svg(e) for e in rl.edges)
    repo_nodes = "".join(_node_svg(n) for n in rl.nodes)
    doc_nodes = "".join(_doc_svg(d) for d in atlas.docs)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {atlas.width:.2f} {atlas.height:.2f}" '
        f'width="{atlas.width:.2f}" height="{atlas.height:.2f}">'
        f'{defs}{style}<g id="viewport">{kedges}{repo_edges}{repo_nodes}{doc_nodes}</g></svg>'
    )
