"""Assemble the self-contained atlas dashboard document."""
from __future__ import annotations

import json

from ..knowledge.markdown import render_markdown
from .theme import css_variables
from .atlas_assets import ATLAS_CSS, ATLAS_JS


def _backlinks(pack: dict) -> dict:
    out: dict[str, list] = {}
    for e in sorted(pack.get("knowledge_edges", []), key=lambda e: (e["to"], e["from"], e["type"])):
        out.setdefault(e["to"], []).append({"from": e["from"], "type": e["type"]})
    return out


def render_atlas_html(pack: dict, docs: list, *, svg: str, include_external: bool = True) -> str:
    rendered = {d.rel_path: render_markdown(d.body) for d in sorted(docs, key=lambda d: d.rel_path)}
    data = dict(pack)
    data["doc_html"] = rendered
    data["backlinks"] = _backlinks(pack)
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>index · atlas</title>"
        f"<style>{css_variables()}{ATLAS_CSS}</style></head><body>"
        '<main><section id="stage">'
        '<div class="controls">'
        '<input type="search" id="search" placeholder="search repos + docs…" aria-label="search">'
        '<button class="chip" id="zoom-reset">reset view</button>'
        '<button class="chip" id="focus-clear">clear focus</button>'
        '<button class="chip" id="toggle-mentions" aria-pressed="true">mentions</button>'
        "</div>"
        '<div id="trail"></div>'
        f"{svg}</section>"
        '<aside><div id="detail">Select a node.</div></aside></main>'
        f"<script>const DATA = {blob};{ATLAS_JS}</script>"
        "</body></html>"
    )
