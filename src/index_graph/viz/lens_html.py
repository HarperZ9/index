"""The Context Lens: a self-contained page that shows what an agent's context
budget actually holds, and what it drops and why, as you move the budget.

No other map tool renders this. Obsidian shows notes; graph tools show nodes.
This shows a SELECTION under a token budget: drag the slider and repos move
between RETAINED and OMITTED live, each omission carrying its failure code
(budget_exceeded / outside_focus_or_budget). The replay runs the exact greedy
rule from context/lens.py in the browser over the pack's own numbers, so the
frontier the slider draws is the frontier the CLI would emit. Zero runtime
deps, deterministic, offline; the receipt hash is printed on the page.
"""
from __future__ import annotations

import html
import json

_CSS = """
:root{--bg:#f4f3ef;--panel:rgba(255,255,255,.6);--ink:#0b0c0e;--muted:#585c64;
--hair:rgba(11,12,14,.14);--accent:#4636e8;--in:#1f8a55;--out:#b23b3b;
--mono:ui-monospace,SFMono-Regular,Consolas,monospace;--body:Arial,Helvetica,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body)}
header{padding:1.1rem 1.4rem .6rem}
h1{font:600 1.15rem var(--body);margin:0 0 .15rem}
.sub{color:var(--muted);font-size:.82rem;max-width:70ch}
.rail{display:flex;gap:1rem;align-items:center;flex-wrap:wrap;padding:.5rem 1.4rem 0}
.rail label{font:600 .78rem var(--mono)}
input[type=range]{flex:1;min-width:14rem;accent-color:var(--accent)}
.gauge{font:600 .95rem var(--mono)}
.gauge b{color:var(--accent)}
.bar{height:10px;border-radius:6px;background:rgba(11,12,14,.10);margin:.5rem 1.4rem 0;overflow:hidden}
.bar i{display:block;height:100%;background:var(--accent);transition:width .08s linear}
.bar.over i{background:var(--out)}
main{display:grid;grid-template-columns:1fr 1fr;gap:1rem;padding:1rem 1.4rem 2rem}
section{background:var(--panel);border:1px solid var(--hair);border-radius:10px;padding:.7rem .8rem;min-height:60vh}
section h2{font:600 .8rem var(--mono);margin:.1rem 0 .6rem;letter-spacing:.02em;display:flex;justify-content:space-between}
.tag{font:600 .72rem var(--mono);padding:.05em .5em;border-radius:5px}
.tag.in{color:var(--in);border:1px solid var(--in)}
.tag.out{color:var(--out);border:1px solid var(--out)}
.row{border:1px solid var(--hair);border-radius:8px;padding:.45rem .55rem;margin-bottom:.4rem;
background:rgba(255,255,255,.5);transition:transform .12s ease,opacity .12s ease}
.row .n{font:600 .92rem var(--body)}
.row .m{font:.72rem var(--mono);color:var(--muted);margin-top:.15rem;display:flex;gap:.7rem;flex-wrap:wrap}
.row .code{color:var(--out);font-weight:600}
.row.just{animation:flash .5s ease}
@keyframes flash{from{background:rgba(70,54,232,.16)}to{background:rgba(255,255,255,.5)}}
.empty{color:var(--muted);font-style:italic;font-size:.82rem;padding:.5rem}
footer{padding:0 1.4rem 2rem;color:var(--muted);font:.72rem var(--mono);word-break:break-all}
.verdict{font:600 .78rem var(--mono);padding:.1em .55em;border-radius:5px;border:1px solid var(--hair)}
.verdict.MATCH{color:var(--in);border-color:var(--in)}
.verdict.UNVERIFIABLE{color:var(--out);border-color:var(--out)}
@media(max-width:760px){main{grid-template-columns:1fr}}
"""

_JS = r"""
const P=LENS,ORDER=P.replay.order,BASE=P.replay.base_tokens;
const el=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const COST={};ORDER.forEach(o=>COST[o.name]=o.cost);
// omission reasons the ENVELOPE assigns to repos outside the scoped candidate set
const OUTSIDE={};(P.envelope.omitted||[]).forEach(o=>{if(o.reason!=='budget_exceeded')OUTSIDE[o.name]=o.reason;});
let prevIn=new Set();
function replay(budget){                 // MIRRORS context/lens.py replay_retained
 const keep=[];let approx=BASE;
 for(const o of ORDER){if(approx+o.cost<=budget||keep.length===0){keep.push(o.name);approx+=o.cost;}}
 return{keep:new Set(keep),approx};
}
function rowHTML(o,omittedCode){
 const meta=[`~${o.cost} tok`,`in:${o.salience.in_degree}`,`out:${o.salience.out_degree}`,
  (o.roles&&o.roles.length?o.roles.join('/'):'')].filter(Boolean);
 if(omittedCode)meta.push(`<span class="code">${esc(omittedCode)}</span>`);
 return `<div class="row" data-n="${esc(o.name)}"><div class="n">${esc(o.name)}</div>`+
  `<div class="m">${meta.map(esc).join(' · ').replace('&lt;span','<span').replace('&lt;/span&gt;','</span>').replace('class=&quot;code&quot;&gt;','class="code">')}</div>`+
  (o.description?`<div class="m">${esc(o.description).slice(0,90)}</div>`:'')+`</div>`;
}
function render(budget){
 const{keep,approx}=replay(budget);
 const inRepos=[],outRepos=[];
 ORDER.forEach(o=>{(keep.has(o.name)?inRepos:outRepos).push(o);});
 el('#kept').innerHTML=inRepos.length?inRepos.map(o=>rowHTML(o,null)).join(''):'<div class="empty">nothing fits — lower bound is one item</div>';
 el('#drop').innerHTML=outRepos.length?outRepos.map(o=>rowHTML(o,OUTSIDE[o.name]||'budget_exceeded')).join(''):'<div class="empty">everything fits at this budget</div>';
 // flash rows that just crossed the frontier into RETAINED
 inRepos.forEach(o=>{if(!prevIn.has(o.name)){const r=el(`#kept .row[data-n="${CSS.escape(o.name)}"]`);if(r)r.classList.add('just');}});
 prevIn=keep;
 el('#in-count').textContent=inRepos.length;el('#out-count').textContent=outRepos.length;
 const pct=Math.min(100,Math.round(approx/budget*100));
 el('#fill').style.width=pct+'%';el('#bar').classList.toggle('over',approx>budget);
 el('#used').textContent=approx;el('#bud').textContent=budget;
 const over=approx>budget&&inRepos.length>1;
 el('#verdict').textContent=over?'UNVERIFIABLE':'MATCH';
 el('#verdict').className='verdict '+(over?'UNVERIFIABLE':'MATCH');
}
const slider=el('#budget');
slider.addEventListener('input',()=>{el('#bval').textContent=slider.value;render(+slider.value);});
render(+slider.value);
"""


def render_lens_html(lens: dict) -> str:
    env = lens["envelope"]
    order = lens["replay"]["order"]
    costs = [o["cost"] for o in order]
    total = sum(costs) + lens["replay"]["base_tokens"]
    built = env["budget"]["token_budget"]
    lo = max(1, min(costs) if costs else 1)
    hi = max(total, built)
    focus = env["focus"]["repo"]
    scope = f"focus: {html.escape(str(focus))}" if focus else "whole workspace"
    data = json.dumps(lens, separators=(",", ":"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Context Lens — {html.escape(str(env['root']))}</title>
<style>{_CSS}</style></head><body>
<header>
<h1>Context Lens <span id="verdict" class="verdict MATCH">MATCH</span></h1>
<div class="sub">What a token budget actually holds for an agent on this workspace, and what it
drops and why. Drag the budget: repos cross between retained and omitted live, replaying the
same greedy selection the <code>index context-envelope</code> CLI emits. {scope}. Zero
dependencies, deterministic, offline.</div>
</header>
<div class="rail">
<label for="budget">token budget <b id="bval">{built}</b></label>
<input type="range" id="budget" min="{lo}" max="{hi}" value="{built}" step="1">
<span class="gauge"><b id="used">0</b>/<span id="bud">{built}</span> tok</span>
</div>
<div class="bar" id="bar"><i id="fill"></i></div>
<main>
<section><h2>RETAINED <span class="tag in">in context · <span id="in-count">0</span></span></h2>
<div id="kept"></div></section>
<section><h2>OMITTED <span class="tag out">dropped · <span id="out-count">0</span></span></h2>
<div id="drop"></div></section>
</main>
<footer>receipt sha256: {html.escape(lens['receipt_sha256'])} &nbsp;·&nbsp; re-check: {html.escape(env['recheck']['command'])}</footer>
<script>const LENS={data};{_JS}</script>
</body></html>"""
