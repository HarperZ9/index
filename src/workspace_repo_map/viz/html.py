"""Render the hero: a single self-contained interactive dashboard."""
from __future__ import annotations

import json

from .theme import css_variables

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
"""

_JS = """
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
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
 const sig=e=>(e.signals||[]).map(s=>`${s.file}${s.line?':'+s.line:''} ${s.kind}`).join('; ');
 $('#detail').innerHTML=`<h3>${name}</h3><div>roles: ${(DATA.roles[name]||[]).join(', ')||'—'}</div>
 <div>in ${ (DATA.salience[name]||{}).in_degree||0 } · out ${ (DATA.salience[name]||{}).out_degree||0 }</div>
 <h4>depends on</h4>${outs.map(e=>`<div>${e.target_name} [${e.confidence}] <small>${sig(e)}</small></div>`).join('')||'—'}
 <h4>depended on by</h4>${ins.map(e=>`<div>${e.from} [${e.confidence}]</div>`).join('')||'—'}`;}
function wire(){
 $('#search').addEventListener('input',e=>{state.q=e.target.value.toLowerCase();apply();});
 $$('.chip[data-role]').forEach(c=>c.addEventListener('click',()=>{
  const r=c.dataset.role;state.roles.has(r)?state.roles.delete(r):state.roles.add(r);
  c.setAttribute('aria-pressed',state.roles.has(r));apply();}));
 $$('.node').forEach(g=>{const pick=()=>{$$('.node').forEach(n=>n.classList.remove('sel'));
  g.classList.add('sel');detail(g.dataset.name);};
  g.addEventListener('click',pick);g.addEventListener('keydown',e=>{if(e.key==='Enter')pick();});});
 apply();}
document.addEventListener('DOMContentLoaded',wire);
"""


def render_html(pack: dict, *, svg: str, charts: dict[str, str]) -> str:
    data = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    roles = sorted({(rs or ["isolated"])[0] for rs in pack.get("roles", {}).values()})
    chips = "".join(
        f'<button class="chip" data-role="{r}" aria-pressed="false">{r}</button>' for r in roles
    )
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>workspace-repo-map · context</title>"
        f"<style>{css_variables()}{_CSS}</style></head><body>"
        '<main><section id="stage">'
        f'<div class="controls"><input type="search" id="search" '
        f'placeholder="filter repos…" aria-label="filter repos">{chips}</div>'
        f"{svg}</section>"
        '<aside><div id="detail">Select a node.</div>'
        f'<h4>confidence</h4>{charts["confidence"]}'
        f'<h4>roles</h4>{charts["roles"]}'
        f'{charts["fanio"]}</aside></main>'
        f"<script>const DATA = {data};{_JS}</script>"
        "</body></html>"
    )
