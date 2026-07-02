"""Render the wiki pack to one self-contained HTML file with client-side nav.

Follows the atlas posture: no external scripts, styles, or fonts; every
untrusted string is escaped server-side; doc markdown arrives pre-rendered
by the escaping-safe renderer; the sealed pack is embedded as a JSON data
island (with ``<`` escaped) so ``index wiki --verify`` can read it back.
"""
from __future__ import annotations

import json
from html import escape

from ..viz.theme import css_variables
from .seal import EMBED_CLOSE, EMBED_OPEN

_CSS = (
    "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);"
    "font-family:var(--font-body)}"
    "header{padding:.7rem 1rem;border-bottom:1px solid var(--hairline);"
    "font-family:var(--font-mono);font-size:.85rem}"
    "main{display:grid;grid-template-columns:260px 1fr;min-height:100vh}"
    "nav{border-right:1px solid var(--hairline);padding:1rem;font-family:var(--font-mono);"
    "font-size:.8rem;overflow:auto}"
    "nav a{display:block;color:var(--ink);text-decoration:none;padding:.15rem .3rem;"
    "border-radius:4px;word-break:break-all}"
    "nav a.active{background:var(--accent);color:var(--bg)}"
    "#pages{padding:1rem 1.5rem;overflow:auto}"
    "section.page footer{margin-top:1.2rem;padding-top:.5rem;border-top:1px solid "
    "var(--hairline);font-family:var(--font-mono);font-size:.72rem;color:var(--muted)}"
    "table{border-collapse:collapse}th,td{border:1px solid var(--hairline);"
    "padding:.2em .6em;text-align:left}"
    ".ev{font-family:var(--font-mono);font-size:.78em;color:var(--muted)}"
    ".label{font-family:var(--font-mono);font-size:.78rem;color:var(--muted)}"
    "article{border-top:1px solid var(--hairline);margin-top:1rem;padding-top:.5rem}"
    ".md pre{background:rgba(255,255,255,.55);border:1px solid var(--hairline);"
    "padding:.5em;overflow:auto}"
    "svg{max-width:100%;height:auto}"
    "@media(max-width:820px){main{grid-template-columns:1fr}nav{border-right:none}}"
)

_JS = (
    "const links=[...document.querySelectorAll('[data-target]')];"
    "function show(t){document.querySelectorAll('.page').forEach("
    "s=>{s.hidden=(s.id!==t);});"
    "links.forEach(a=>{a.classList.toggle('active',a.dataset.target===t);});}"
    "links.forEach(a=>a.addEventListener('click',"
    "ev=>{ev.preventDefault();show(a.dataset.target);}));"
    "show('page-0');"
)


def _loc(e: dict) -> str:
    line = e.get("line")
    return f"{e['file']}:{line}" if line else str(e["file"])


def _footer(page: dict) -> str:
    n = page["boundary"]["evidence_count"]
    return ("<footer>structure derived from the dependency graph; no generated "
            f"prose; evidence shown: {n} file:line reference(s)</footer>")


def _overview_section(p: dict) -> str:
    rows = [("repo", p["repo"]), ("commit", p["commit"]),
            ("ecosystems", ", ".join(p["ecosystems"]) or "none"),
            ("modules", str(p["module_count"])),
            ("internal edges", str(p["internal_edge_count"])),
            ("cycles", str(p["cycle_count"])),
            ("entry points (no internal importer)",
             ", ".join(p["entry_points"]) or "none")]
    table = "".join(f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>"
                    for k, v in rows)
    inventory = "".join(f"<li><code>{escape(d)}</code></li>"
                        for d in p["doc_paths"]) or "<li>none</li>"
    cov = p["coverage"]
    coverage = ("complete" if cov["complete"] else
                f"{len(cov['parse_errors'])} unparsed file(s), "
                f"{len(cov['dynamic_imports'])} dynamic import(s) not followed")
    return (f"<h2>{escape(p['title'])}</h2><table>{table}</table>"
            f"<h3>doc inventory ({p['doc_count']})</h3><ul>{inventory}</ul>"
            f"<p class=\"label\">graph coverage: {escape(coverage)}</p>")


def _edge_list(items: list[dict], key: str) -> str:
    lis = "".join(
        f"<li><code>{escape(e[key])}</code> "
        f"<span class=\"ev\">{escape(_loc(e))}</span></li>" for e in items)
    return f"<ul>{lis}</ul>" if lis else "<p>none</p>"


def _module_section(p: dict) -> str:
    cycles = "".join(f"<li><code>{escape(' -> '.join(c))}</code></li>"
                     for c in p["cycles"])
    return (f"<h2>{escape(p['title'])}</h2>"
            f"<p class=\"label\">{escape(p['path'])} ({escape(p['language'])})</p>"
            f"<h3>imports</h3>{_edge_list(p['imports'], 'to')}"
            f"<h3>dependents</h3>{_edge_list(p['dependents'], 'from')}"
            + (f"<h3>cycle membership</h3><ul>{cycles}</ul>" if cycles else ""))


def _via_list(groups: list[dict], key: str) -> str:
    out = []
    for group in groups:
        vias = "".join(
            f"<li><code>{escape(v['from'])} -&gt; {escape(v['to'])}</code> "
            f"<span class=\"ev\">{escape(_loc(v))}</span></li>" for v in group["via"])
        out.append(f"<li><code>{escape(group[key])}</code><ul>{vias}</ul></li>")
    return f"<ul>{''.join(out)}</ul>" if out else "<p>none</p>"


def _package_section(p: dict) -> str:
    mods = "".join(f"<li><code>{escape(m)}</code></li>" for m in p["modules"])
    return (f"<h2>{escape(p['title'])}</h2>"
            f"<h3>modules ({len(p['modules'])})</h3><ul>{mods}</ul>"
            f"<h3>imports</h3>{_via_list(p['imports'], 'to')}"
            f"<h3>dependents</h3>{_via_list(p['dependents'], 'from')}")


def _architecture_section(p: dict) -> str:
    return (f"<h2>{escape(p['title'])}</h2>"
            f"<p class=\"label\">rendered from the real {escape(p['granularity'])} "
            f"graph, {p['edge_count']} evidence-backed edge(s); never inferred</p>"
            f"{p['svg']}"
            f"<details><summary>mermaid source</summary>"
            f"<pre>{escape(p['mermaid'])}</pre></details>")


def _docs_section(p: dict) -> str:
    articles = "".join(
        f"<article><h3>{escape(d['title'])} <code>{escape(d['path'])}</code></h3>"
        f"<div class=\"md\">{d['html']}</div></article>" for d in p["docs"])
    return (f"<h2>{escape(p['title'])}</h2>"
            "<p class=\"label\">authored by humans; joined in verbatim and "
            "rendered offline, never rewritten</p>" + (articles or "<p>none</p>"))


_SECTIONS = {"overview": _overview_section, "module": _module_section,
             "package": _package_section, "architecture": _architecture_section,
             "docs": _docs_section}


def render_wiki_html(pack: dict) -> str:
    nav, sections = [], []
    for i, page in enumerate(pack["pages"]):
        target = f"page-{i}"
        nav.append(f'<a href="#" data-target="{target}">{escape(page["title"])}</a>')
        body = _SECTIONS[page["kind"]](page)
        sections.append(f'<section class="page" id="{target}">{body}{_footer(page)}</section>')
    blob = json.dumps(pack, sort_keys=True,
                      separators=(",", ":")).replace("<", "\\u003c")
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>index | wiki | {escape(pack['repo'])}</title>"
        f"<style>{css_variables()}{_CSS}</style></head><body>"
        f"<header>index wiki: <strong>{escape(pack['repo'])}</strong> "
        f"pinned to <code>{escape(pack['commit'])}</code></header>"
        f'<main><nav aria-label="wiki pages">{"".join(nav)}</nav>'
        f'<div id="pages">{"".join(sections)}</div></main>'
        f"{EMBED_OPEN}{blob}{EMBED_CLOSE}"
        f"<script>{_JS}</script>"
        "</body></html>"
    )
