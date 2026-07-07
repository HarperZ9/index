"""Assemble the self-contained workbench document.

One page, five views over one sealed pack: Overview (the workspace at a
glance + the context basket), Map (the interactive two-layer atlas with a
live context-lens overlay), Docs (the derived knowledge layer), Context Lens
(the budget frontier), Health (cycles, warnings, salience audit, freshness
fingerprints). Command palette on Ctrl/Cmd-K, full state in the URL hash,
zero runtime dependencies, receipt printed in the footer.
"""
from __future__ import annotations

import html
import json

from .workbench_assets import WB_CSS
from .workbench_js import WB_JS_CORE
from .workbench_js2 import WB_JS_UX

_MAP_EXTRA_CSS = (
    "#map-stage .node.lens-out,#map-stage .docnode.lens-out{opacity:.14}"
    "#map-stage .node.sel rect{stroke:#4636e8;stroke-width:2.5}"
    "#map-stage .docnode.sel rect{stroke:#4636e8;stroke-width:2}"
)


def _stat(n, label, cls="") -> str:
    return (f'<div class="stat {cls}"><div class="n">{n}</div>'
            f'<div class="l">{label}</div></div>')


def _overview(wb: dict) -> str:
    s = wb["summary"]
    roles = " · ".join(f"{k} {v}" for k, v in s["role_counts"].items())
    tops = ", ".join(s["top_salience"][:5])
    return f"""<div class="hero">
<h2>{s['repos']} repos, {s['docs']} docs, one verified map.</h2>
<p>Everything below is derived from file:line evidence at <code>{html.escape(wb['root'])}</code>
and sealed under receipt <code>{html.escape(wb['receipt_sha256'][:16])}…</code>.
Press <kbd>Ctrl</kbd>+<kbd>K</kbd> for anything; pin repos into the context basket and the
exact <code>index context-envelope</code> command is written for you.</p></div>
<div class="cards">
{_stat(s['repos'], 'repos')}{_stat(s['docs'], 'docs')}
{_stat(s['relations'], 'dependency edges')}{_stat(s['knowledge_edges'], 'knowledge edges')}
{_stat(s['cycles'], 'cycles', 'iris' if s['cycles'] else '')}
{_stat(s['warnings'], 'warnings', 'iris' if s['warnings'] else '')}
</div>
<div class="kv"><span>roles: {html.escape(roles)}</span></div>
<div class="kv"><span>highest-salience: {html.escape(tops)}</span></div>
<div class="basketbar" id="basketbar"></div>
<h4 style="font:600 .7rem var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)">all repos</h4>
<ul class="rowlist">""" + "".join(
        f'<li><span class="nm navlink" data-kind="repo" data-id="{html.escape(r["name"])}" '
        f'onclick="select(\'repo\',{json.dumps(r["name"])})">{html.escape(r["name"])}</span>'
        f'<span class="mt">in {r["in_degree"]} · out {r["out_degree"]}'
        f'{" · " + html.escape(", ".join(r["roles"])) if r["roles"] else ""}</span></li>'
        for r in wb["repos"]) + "</ul>"


def _docs_view(wb: dict) -> str:
    rows = "".join(
        f'<li><span class="nm" onclick="select(\'doc\',{json.dumps(d["id"])})">'
        f'{html.escape(d["title"])}</span><span class="mt">{html.escape(d["id"])}</span></li>'
        for d in wb["docs"])
    dm = wb["doc_meta"]
    budget_line = ""
    if dm["bodies_embedded"] < dm["total"]:
        budget_line = (f' Page-weight budget: <b>{dm["bodies_embedded"]}</b> of '
                       f'<b>{dm["total"]}</b> bodies embedded (most-connected first); '
                       f'the list and search below cover all of them.')
    return (f'<div class="hero"><h2>The knowledge layer</h2>'
            f'<p>{len(wb["docs"])} docs discovered and linked to the map by '
            f'<b>describes / links-to / mentions</b> edges — derived, not hand-filed. '
            f'Select one to read it with backlinks in the panel.{budget_line}</p></div>'
            f'<ul class="rowlist">{rows or "<li><span class=mt>no docs discovered</span></li>"}</ul>')


def _lens_view(wb: dict) -> str:
    order = wb["lens"]["replay"]["order"]
    total = sum(o["cost"] for o in order) + wb["lens"]["replay"]["base_tokens"]
    built = wb["lens"]["budget"]["token_budget"]
    return f"""<div class="hero"><h2>What fits in the context budget
<span class="verdictchip {wb['lens']['verdict']}" id="lens-verdict">{wb['lens']['verdict']}</span></h2>
<p>Repos in the exact rank the envelope fills them. Drag the budget: the frontier slides and
rows cross between retained and omitted, replaying the same greedy rule
<code>index context-envelope</code> runs — what you see is what an agent gets. The Map view
can overlay this frontier onto the graph.</p></div>
<div class="lensrail">
<label for="lens-slider">token budget</label>
<input type="range" id="lens-slider" min="1" max="{max(total, built)}" value="{built}" step="1"
 aria-label="token budget">
<span class="big" id="lens-bval">{built}</span>
<span class="mt" style="font:.76rem var(--mono);color:var(--muted)">
<span id="lens-used">0</span> used incl. base {wb['lens']['replay']['base_tokens']}</span>
</div>
<div id="lens-stack"></div>"""


def _health(wb: dict) -> str:
    f = wb["freshness"]
    cycles = "".join(f'<span class="cycchip">{html.escape(" → ".join(c + [c[0]]))}</span>'
                     for c in wb["cycles"]) or '<span class="mt">none — the graph is acyclic</span>'
    warns = "".join(f'<div class="warnrow">{html.escape(w)}</div>'
                    for w in (wb["warnings"] + wb["knowledge_warnings"])[:40]) \
        or '<div class="mt">none</div>'
    audit = "".join(
        f'<div class="warnrow">[{html.escape(a.get("kind", ""))}] {html.escape(a.get("node", ""))}: '
        f'{html.escape(a.get("note", ""))}</div>'
        for a in wb["salience_audit"]) or '<div class="mt">no salience-faithfulness warnings</div>'
    fps = "".join(f'<li><span class="nm">{html.escape(n)}</span>'
                  f'<span class="mt fp">{html.escape(h)}</span></li>'
                  for n, h in sorted(f["repos"].items()))
    return f"""<div class="hero"><h2>Structural health &amp; freshness</h2>
<p>What one pass can honestly verify: cycles, warnings, and the salience audit are structural
facts of the current graph. The fingerprints below are the <b>baseline</b> a later run diffs
against — a FRESH/STALE verdict needs a prior snapshot, so none is claimed here.</p>
<p class="mt" style="font:.76rem var(--mono);color:var(--muted)">re-check: <code>{html.escape(f['recheck'])}</code></p></div>
<h4>dependency cycles</h4><div>{cycles}</div>
<h4>warnings</h4>{warns}
<h4>salience audit</h4>{audit}
<h4>workspace fingerprint</h4>
<div class="fp">root {html.escape(f['root_sha256'])}</div>
<ul class="rowlist">{fps}</ul>"""


def _spine(wb: dict) -> str:
    sp = wb["spine"]
    if not sp["tools"]:
        return (f'<div class="hero"><h2>The operator spine</h2>'
                f'<p>No flagship envelopes were supplied to this build, so nothing is '
                f'claimed about peers. {html.escape(sp["capture"])}.</p></div>')
    ring = "".join(
        f'<div class="dep"><span class="to">{html.escape(e["from"])} '
        f'<span style="color:var(--iris)">→</span> {html.escape(e["to"])}</span>'
        f'<span class="conf">{html.escape(e["action"])}</span>'
        f'<div class="ev">{html.escape(e["reason"])}</div></div>'
        for e in sp["ring"]) or '<div class="mt">no next_actions declared</div>'
    tools = "".join(
        f'<div class="dep"><span class="to">{html.escape(t["tool"])}</span>'
        f'<span class="conf">v{html.escape(t["version"])} · {html.escape(t["command"])}</span>'
        f'<span class="verdictchip {html.escape(t["status"])}" style="margin-left:.5em">'
        f'{html.escape(t["status"])}</span>'
        + "".join(f'<div class="ev">{html.escape(c["name"])} — {html.escape(c["status"])}</div>'
                  for c in t["checks"]) + "</div>"
        for t in sp["tools"])
    peers = "".join(
        f'<div class="dep"><span class="to">{html.escape(s["peer"])}</span>'
        f'<span class="conf">{html.escape(s["surface"])} · {s["entries"]} entries</span>'
        f'<div class="ev">inspect: {html.escape(s["inspect"])}</div></div>'
        for s in sp["peer_surfaces"]) or '<div class="mt">none detected under .telos/</div>'
    skipped = "".join(
        f'<div class="warnrow">{html.escape(s["file"])}: {html.escape(s["reason"])}</div>'
        for s in sp["skipped"])
    return (f'<div class="hero"><h2>The operator spine</h2>'
            f'<p>The flagships are aware of each other by protocol: every doctor/status '
            f'envelope declares <code>next_actions</code> handing off to a peer. This view '
            f'renders the captured envelopes and the awareness ring they form — receipts '
            f'from the tools themselves, not this page’s opinion.</p></div>'
            f'<h4>awareness ring (who hands off to whom)</h4>{ring}'
            f'<h4>captured envelopes</h4>{tools}'
            f'<h4>peer surfaces on disk</h4>{peers}'
            + (f'<h4>skipped inputs (fail closed)</h4>{skipped}' if skipped else ""))


def render_workbench_html(wb: dict) -> str:
    svg = wb["svg"]
    data = {k: v for k, v in wb.items() if k != "svg"}
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    root = html.escape(str(wb["root"]))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>index workbench — {root}</title>
<style>{WB_CSS}{_MAP_EXTRA_CSS}</style></head><body>
<div class="app">
<div class="top">
<span class="brand">index · workbench</span>
<nav class="modes" aria-label="views">
<button class="mode" id="mode-overview" aria-pressed="true">Overview</button>
<button class="mode" id="mode-map" aria-pressed="false">Map</button>
<button class="mode" id="mode-docs" aria-pressed="false">Docs</button>
<button class="mode" id="mode-lens" aria-pressed="false">Context Lens</button>
<button class="mode" id="mode-health" aria-pressed="false">Health</button>
<button class="mode" id="mode-spine" aria-pressed="false">Spine</button>
</nav>
<button class="searchbtn" id="searchbtn"><span>search repos, docs, actions…</span><kbd>Ctrl K</kbd></button>
<button class="basketbtn" id="basketbtn" data-n="0">basket <span class="n" id="basket-n">0</span></button>
</div>
<div class="main">
<div class="stage" tabindex="-1">
<div class="view on" id="view-overview">{_overview(wb)}</div>
<div class="view" id="view-map"><div id="map-stage">
<div class="maptools">
<button class="chip" id="zoom-fit">fit</button>
<button class="chip" id="focus-clear">clear focus</button>
<button class="chip" id="toggle-lens-overlay" aria-pressed="false">context overlay</button>
</div>
<div class="legendbar">
<span class="lg"><i style="background:#4636e8"></i>in budget (overlay)</span>
<span class="lg">click: inspect</span><span class="lg">double-click: neighborhood</span>
<span class="lg">wheel: zoom</span>
<span class="lg">map draws {wb['doc_meta']['map_docs']} of {wb['doc_meta']['total']} docs</span>
</div>
{svg}</div></div>
<div class="view" id="view-docs">{_docs_view(wb)}</div>
<div class="view" id="view-lens">{_lens_view(wb)}</div>
<div class="view" id="view-health">{_health(wb)}</div>
<div class="view" id="view-spine">{_spine(wb)}</div>
</div>
<aside><div class="crumbs" id="crumbs"></div>
<div id="detail"><p class="mt">Select a repo or doc — click the map, a row, or press
<kbd>Ctrl</kbd>+<kbd>K</kbd>. Keys: <b>1-5</b> views · <b>/</b> palette · <b>p</b> pin.</p></div>
</aside>
</div>
</div>
<div class="palette" id="palette" role="dialog" aria-label="command palette">
<div class="pbox"><input id="pinput" placeholder="jump to a repo, doc, or action…"
 autocomplete="off" spellcheck="false">
<div class="presults" id="presults"></div>
<div class="phint"><span><kbd>↑↓</kbd> navigate</span><span><kbd>enter</kbd> run</span>
<span><kbd>esc</kbd> close</span></div></div>
</div>
<div class="toast" id="toast"></div>
<footer class="receipt">receipt sha256 {html.escape(wb['receipt_sha256'])} · root {root} ·
re-derive: index workbench --root . --out workbench.html</footer>
<script>const DATA={blob};{WB_JS_CORE}{WB_JS_UX}</script>
</body></html>"""
