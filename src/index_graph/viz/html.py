"""Render the hero: a single self-contained interactive dashboard."""
from __future__ import annotations

import json
from xml.sax.saxutils import escape

from .theme import css_variables, ROLE_COLOR, THEME

_CSS = """
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:var(--font-body)}main{display:grid;grid-template-columns:1fr 340px;
min-height:100vh}#stage{overflow:auto;padding:1rem}aside{border-left:1px solid
var(--hairline);padding:1rem;font-family:var(--font-mono);font-size:.82rem}
.controls{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.8rem}
.chip{cursor:pointer;border:1px solid var(--hairline);border-radius:6px;
padding:.2em .5em;background:transparent;color:var(--ink)}
.chip[aria-pressed=true]{background:var(--accent);color:var(--bg)}
input[type=search]{width:100%;padding:.4em;background:transparent;color:var(--ink);
border:1px solid var(--hairline);border-radius:6px;margin-bottom:.6rem}
.node.dim{opacity:.12}.edge.dim{opacity:.05}
.node:focus rect,.node.sel rect{stroke:var(--accent);stroke-width:2}
.row{display:flex;align-items:center;gap:.4rem;margin:.15rem 0}
.lbl{width:6.5rem;opacity:.85}.bar{height:.7rem;background:var(--teal);border-radius:3px}
.num{opacity:.7}h4{margin:.6rem 0 .2rem;color:var(--gold)}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
@media(max-width:820px){main{grid-template-columns:1fr}aside{border-left:none}}
.tip{position:fixed;pointer-events:none;z-index:9;max-width:24rem;background:var(--bg);
border:1px solid var(--accent);border-radius:6px;padding:.4em .6em;font-family:var(--font-mono);
font-size:.74rem;line-height:1.35}.tip[hidden]{display:none}
.legend{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;margin:.2rem 0 .8rem;
font-family:var(--font-mono);font-size:.72rem;opacity:.85}.legend b{color:var(--gold)}
.leg{display:inline-flex;align-items:center;gap:.3rem}.leg i{width:.8rem;height:.8rem;
border-radius:2px;display:inline-block}.leg i.ln{height:0;width:1.2rem;border-top:2px solid}
.leg i.ln.d5{border-top-style:dashed}.leg i.ln.d2{border-top-style:dotted}
"""

_JS = """
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={q:'',roles:new Set(),conf:new Set(),ext:true};
const idx={};DATA.repos.forEach(r=>idx[r.name]=r);
function match(name){const r=idx[name];if(!r)return state.ext;
 if(state.q&&!name.toLowerCase().includes(state.q))return false;
 const role=(DATA.roles[name]||['isolated'])[0];
 if(state.roles.size&&!state.roles.has(role))return false;return true;}
function apply(){$$('.node').forEach(g=>{g.classList.toggle('dim',!match(g.dataset.name));});
 $$('.edge').forEach(p=>{const on=match(p.dataset.from)&&match(p.dataset.to)&&
  (!state.conf.size||state.conf.has(p.className.baseVal.match(/edge-(high|moderate|low)/)?.[1]));
  p.classList.toggle('dim',!on);});}
function detail(name){const r=idx[name]||{name,ecosystems:[],markers:[]};
 const outs=DATA.relations.filter(e=>e.from===name);
 const ins=DATA.relations.filter(e=>e.to===name);
 const sig=e=>(e.signals||[]).map(s=>`${esc(s.file)}${s.line?':'+esc(s.line):''} ${esc(s.kind)}`).join('; ');
 $('#detail').innerHTML=`<h3>${esc(name)}</h3><div>roles: ${esc((DATA.roles[name]||[]).join(', '))||'none'}</div>
 <div>in ${ (DATA.salience[name]||{}).in_degree||0 } · out ${ (DATA.salience[name]||{}).out_degree||0 }</div>
 <h4>depends on</h4>${outs.map(e=>`<div>${esc(e.target_name)} [${esc(e.confidence)}] <small>${sig(e)}</small></div>`).join('')||'none'}
 <h4>depended on by</h4>${ins.map(e=>`<div>${esc(e.from)} [${esc(e.confidence)}]</div>`).join('')||'none'}`;}
const tip=Object.assign(document.createElement('div'),{className:'tip',hidden:true});
function edgeTip(p,x,y){const sg=JSON.parse(p.getAttribute('data-signals')||'[]');
 const conf=(p.className.baseVal.match(/edge-(high|moderate|low)/)||[])[1]||'declared';
 const ev=sg.map(s=>`${esc(s.file)}${s.line?':'+esc(s.line):''} (${esc(s.kind)})`).join('<br>')||'manifest';
 tip.innerHTML=`<b>${esc(p.dataset.from)} → ${esc(p.dataset.to)}</b> · ${esc(conf)}<br>${ev}`;
 tip.hidden=false;tip.style.left=(x+12)+'px';tip.style.top=(y+12)+'px';}
function nbrs(name){const s=new Set([name]);DATA.relations.forEach(e=>{
 if(e.from===name&&e.to)s.add(e.to);if(e.to===name)s.add(e.from);});return s;}
function highlight(name){const s=nbrs(name);
 $$('.node').forEach(g=>g.classList.toggle('dim',!s.has(g.dataset.name)));
 $$('.edge').forEach(p=>p.classList.toggle('dim',!(s.has(p.dataset.from)&&s.has(p.dataset.to))));}
function wire(){
 $('#search').addEventListener('input',e=>{state.q=e.target.value.toLowerCase();apply();});
 $$('.chip[data-role]').forEach(c=>c.addEventListener('click',()=>{
  const r=c.dataset.role;state.roles.has(r)?state.roles.delete(r):state.roles.add(r);
  c.setAttribute('aria-pressed',state.roles.has(r));apply();}));
 $$('.node').forEach(g=>{const pick=()=>{$$('.node').forEach(n=>n.classList.remove('sel'));
  g.classList.add('sel');detail(g.dataset.name);};
  g.addEventListener('click',pick);g.addEventListener('keydown',e=>{if(e.key==='Enter')pick();});});
 document.body.appendChild(tip);
 $$('.edge').forEach(p=>{p.addEventListener('mousemove',e=>edgeTip(p,e.clientX,e.clientY));
  p.addEventListener('mouseleave',()=>tip.hidden=true);});
 $$('.node').forEach(g=>{g.addEventListener('mouseenter',()=>highlight(g.dataset.name));
  g.addEventListener('mouseleave',apply);});
 apply();}
document.addEventListener('DOMContentLoaded',wire);
"""


def _legend() -> str:
    roles = "".join(
        f'<span class="leg"><i style="background:{c}"></i>{escape(r)}</span>'
        for r, c in ROLE_COLOR.items() if r != "external")
    edges = (
        f'<span class="leg"><i class="ln" style="border-color:{THEME.ok}"></i>high</span>'
        f'<span class="leg"><i class="ln d5" style="border-color:{THEME.gold}"></i>moderate</span>'
        f'<span class="leg"><i class="ln d2" style="border-color:{THEME.muted}"></i>low / external</span>'
        f'<span class="leg"><i class="ln" style="border-color:{THEME.alert}"></i>cycle</span>')
    return (f'<div class="legend"><b>roles</b>{roles}'
            f'<b>edges</b>{edges}</div>')


def _salience_audit_panel(pack: dict) -> str:
    entries = pack.get("salience_audit", [])
    rows = "".join(
        f'<div class="audit-row"><b>{escape(str(e.get("node", "")))}</b>'
        f' [{escape(str(e.get("kind", "")))}]'
        f': {escape(str(e.get("note", "")))}</div>'
        for e in entries
    )
    body = rows if rows else '<div class="audit-row" style="opacity:.5">none</div>'
    return f"<h4>salience audit</h4>{body}"


def render_html(pack: dict, *, svg: str, charts: dict[str, str]) -> str:
    data = json.dumps(pack, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    roles = sorted({(rs or ["isolated"])[0] for rs in pack.get("roles", {}).values()})
    chips = "".join(
        f'<button class="chip" data-role="{r}" aria-pressed="false">{r}</button>' for r in roles
    )
    audit_panel = _salience_audit_panel(pack)
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>index · context</title>"
        f"<style>{css_variables()}{_CSS}</style></head><body>"
        '<main><section id="stage">'
        f'<div class="controls"><input type="search" id="search" '
        f'placeholder="filter repos…" aria-label="filter repos">{chips}</div>'
        f"{_legend()}{svg}</section>"
        '<aside><div id="detail">Select a node.</div>'
        f'<h4>confidence</h4>{charts["confidence"]}'
        f'<h4>roles</h4>{charts["roles"]}'
        f'{charts["fanio"]}'
        f'{audit_panel}</aside></main>'
        f"<script>const DATA = {data};{_JS}</script>"
        "</body></html>"
    )
