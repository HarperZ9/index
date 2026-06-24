"""Render a LayoutModel to a self-contained SVG network graph."""
from __future__ import annotations

import json
from xml.sax.saxutils import escape, quoteattr

from .layout import LayoutModel
from .theme import THEME, svg_style


def _path_d(points: tuple[tuple[float, float], ...]) -> str:
    (m, c1, c2, end) = points
    return (
        f"M{m[0]:.2f},{m[1]:.2f} "
        f"C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {end[0]:.2f},{end[1]:.2f}"
    )


def _edge_svg(edge) -> str:
    classes = ["edge", f"edge-{edge.confidence}"]
    if edge.external:
        classes.append("edge-external")
    if edge.back_edge:
        classes.append("edge-back")
    if getattr(edge, "in_cycle", False):
        classes.append("edge-cycle")
    return (
        (lambda sig: (
            f'<path class={quoteattr(" ".join(classes))} '
            f'data-from={quoteattr(edge.from_repo)} data-to={quoteattr(edge.to_repo)} '
            f'data-signals={sig} '
            f'marker-end="url(#arrow)" d="{_path_d(edge.points)}"/>'
        ))(quoteattr(json.dumps(list(edge.signals), sort_keys=True)))
        if edge.points
        else ""
    )


def _node_svg(node) -> str:
    label = escape(node.name)
    node_classes = "node role-" + node.role + (" cycle" if getattr(node, "in_cycle", False) else "")
    return (
        f'<g class={quoteattr(node_classes)} '
        f'data-name={quoteattr(node.name)} data-role={quoteattr(node.role)} '
        f'data-roles={quoteattr(",".join(node.roles))} '
        f'data-indeg="{node.in_degree}" data-outdeg="{node.out_degree}" '
        f'data-hub="{str(node.hub).lower()}" tabindex="0" '
        f'role="img" aria-label={quoteattr(node.name + " (" + node.role + ")")}>'
        f'<rect x="{node.x:.2f}" y="{node.y:.2f}" width="{node.w:.2f}" '
        f'height="{node.h:.2f}" rx="6"/>'
        f'<text x="{node.x + node.w / 2:.2f}" y="{node.y + node.h / 2 + 4:.2f}" '
        f'text-anchor="middle">{label}</text>'
        f"<title>{label} — {escape(node.role)}</title>"
        f"</g>"
    )


def render_svg(layout: LayoutModel) -> str:
    defs = (
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{THEME.muted}"/></marker></defs>'
    )
    style = f"<style>{svg_style()}</style>"
    bg = f'<rect x="0" y="0" width="{layout.width:.2f}" height="{layout.height:.2f}" fill="{THEME.bg}"/>'
    edges = "".join(_edge_svg(e) for e in layout.edges)
    nodes = "".join(_node_svg(n) for n in layout.nodes)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {layout.width:.2f} {layout.height:.2f}" '
        f'width="{layout.width:.2f}" height="{layout.height:.2f}">'
        f"{defs}{style}{bg}{edges}{nodes}</svg>"
    )
