"""The Context Lens: a self-contained page that shows what an agent's context
budget actually holds, and what it drops and why, as you move the budget.

No other map tool renders this. Obsidian shows notes; graph tools show nodes.
This shows a SELECTION under a token budget: one ordered stack of repos in the
exact rank the greedy fill considers them, with a budget frontier that slides
as you drag the budget. Repos above the frontier are RETAINED; the moment one
crosses below it, it is OMITTED and carries its failure code
(budget_exceeded / outside_focus_or_budget). The replay runs the exact greedy
rule from context/lens.py in the browser over the pack's own numbers, so the
frontier the slider draws is the frontier the CLI would emit. Zero runtime
deps, deterministic, offline; the receipt hash is printed on the page.

Brand: ceramic bg, ink text, one iris accent, mono for receipts — cohesive
with the index atlas. Motion conveys state change only (a repo crossing the
frontier), with a reduced-motion fallback.
"""
from __future__ import annotations

import html
import json

_CSS = """
:root{
 --bg:#f4f3ef;--panel:#fbfaf7;--ink:#0b0c0e;--soft:#2f3238;--muted:#565a62;
 --hair:rgba(11,12,14,.12);--hair2:rgba(11,12,14,.07);
 --iris:#4636e8;--iris-wash:rgba(70,54,232,.08);--iris-line:rgba(70,54,232,.35);
 --drop:#8a5a12;--in-ink:#0b0c0e;
 --mono:ui-monospace,SFMono-Regular,Consolas,"SF Mono",monospace;
 --body:Arial,Helvetica,"Helvetica Neue",sans-serif;
 --e:cubic-bezier(.22,1,.36,1)}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);
 font-size:16px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:2.2rem 1.5rem 3rem}
header{margin-bottom:1.6rem}
.eyebrow{font:600 .72rem/1 var(--mono);letter-spacing:.14em;color:var(--iris);
 text-transform:uppercase;margin:0 0 .55rem}
h1{font:600 1.7rem/1.15 var(--body);margin:0 0 .5rem;letter-spacing:-.02em;text-wrap:balance;
 display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap}
.sub{color:var(--soft);font-size:.92rem;max-width:68ch;margin:0}
.sub code{font:.85em var(--mono);background:var(--hair2);padding:.05em .35em;border-radius:4px}
.verdict{font:600 .68rem/1 var(--mono);letter-spacing:.06em;padding:.35em .6em;border-radius:999px;
 border:1px solid;vertical-align:middle;white-space:nowrap;transition:color .2s,border-color .2s,background .2s}
.verdict[data-v=MATCH]{color:#1f6b45;border-color:rgba(31,107,69,.4);background:rgba(31,107,69,.07)}
.verdict[data-v=UNVERIFIABLE]{color:var(--drop);border-color:rgba(138,90,18,.4);background:rgba(138,90,18,.08)}

.panel{background:var(--panel);border:1px solid var(--hair);border-radius:14px;
 box-shadow:0 1px 0 rgba(11,12,14,.03),0 12px 30px -22px rgba(11,12,14,.35);overflow:hidden}
.rail{display:grid;grid-template-columns:1fr auto;gap:1rem 1.4rem;align-items:center;
 padding:1.1rem 1.3rem;border-bottom:1px solid var(--hair2)}
.slider{grid-column:1/-1;display:flex;align-items:center;gap:1rem}
.slider label{font:600 .74rem/1 var(--mono);letter-spacing:.04em;color:var(--muted);white-space:nowrap}
input[type=range]{flex:1;height:26px;accent-color:var(--iris);cursor:pointer}
input[type=range]:focus-visible{outline:2px solid var(--iris);outline-offset:4px;border-radius:4px}
.readout{display:flex;align-items:baseline;gap:.5rem;font:var(--mono)}
.readout .big{font:600 1.35rem/1 var(--mono);color:var(--iris);letter-spacing:-.01em;
 font-variant-numeric:tabular-nums}
.readout .of{font:.8rem var(--mono);color:var(--muted)}
.legend{display:flex;gap:1.1rem;font:600 .72rem/1 var(--mono);letter-spacing:.03em;flex-wrap:wrap}
.legend b{font-weight:600}
.legend .k{display:inline-flex;align-items:center;gap:.4em;color:var(--muted)}
.legend .dot{width:.7em;height:.7em;border-radius:2px;display:inline-block}
.legend .dot.in{background:var(--iris)}
.legend .dot.out{background:transparent;border:1px solid var(--muted)}
.legend .n{color:var(--ink);font-variant-numeric:tabular-nums}

.stack{list-style:none;margin:0;padding:.3rem 0}
.frontier{position:relative;height:0;margin:0 1.3rem;border-top:1.5px dashed var(--iris-line);
 transition:margin-top .28s var(--e)}
.frontier::after{content:"budget frontier — " attr(data-tok) " tok";position:absolute;right:0;top:-.55rem;
 font:600 .64rem/1 var(--mono);letter-spacing:.05em;color:var(--iris);background:var(--panel);
 padding:.2em .5em;border:1px solid var(--iris-line);border-radius:999px}
.item{display:grid;grid-template-columns:1.7rem 1fr auto;align-items:center;gap:.2rem .9rem;
 padding:.62rem 1.3rem;position:relative;transition:background .24s var(--e),opacity .24s var(--e)}
.item::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--iris);
 transform:scaleY(0);transform-origin:top;transition:transform .26s var(--e)}
.item.in::before{transform:scaleY(1)}
.item+.item{border-top:1px solid var(--hair2)}
.item .rank{font:600 .72rem/1 var(--mono);color:var(--muted);font-variant-numeric:tabular-nums;text-align:right}
.item .name{font:600 .98rem/1.25 var(--body);letter-spacing:-.01em;transition:color .24s}
.item .meta{grid-column:2;font:.74rem/1.4 var(--mono);color:var(--muted);
 display:flex;gap:.85rem;flex-wrap:wrap;margin-top:.12rem}
.item .desc{grid-column:2;font:.82rem/1.4 var(--body);color:var(--soft);margin-top:.15rem;
 max-width:64ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item .cost{font:600 .82rem/1 var(--mono);color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}
.item .code{color:var(--drop);font-weight:600}
.item.in{background:var(--iris-wash)}
.item.out{opacity:.62}
.item.out .name{color:var(--soft)}
.item.cross{animation:cross .5s var(--e)}
@keyframes cross{0%{background:rgba(70,54,232,.22)}100%{background:var(--iris-wash)}}

footer{margin-top:1.3rem;display:flex;flex-direction:column;gap:.35rem;
 font:.72rem/1.5 var(--mono);color:var(--muted);word-break:break-all}
footer .lbl{color:var(--soft);font-weight:600}
@media(max-width:640px){
 .wrap{padding:1.5rem 1rem 2rem}h1{font-size:1.4rem}
 .item .desc{white-space:normal}
 .rail{grid-template-columns:1fr}.legend{justify-content:flex-start}
}
@media(prefers-reduced-motion:reduce){
 *{transition:none!important;animation:none!important}
}
"""

_JS = r"""
const P=LENS,ORDER=P.replay.order,BASE=P.replay.base_tokens;
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const OUTSIDE={};(P.envelope.omitted||[]).forEach(o=>{if(o.reason!=='budget_exceeded')OUTSIDE[o.name]=o.reason;});
function replay(budget){                       // MIRRORS context/lens.py replay_retained
 const keep=new Set();let approx=BASE;
 for(const o of ORDER){if(approx+o.cost<=budget||keep.size===0){keep.add(o.name);approx+=o.cost;}}
 return{keep,approx};
}
// build every row ONCE, in rank order; state is a class toggle so rows glide, never re-mount
const stack=$('#stack');
ORDER.forEach((o,i)=>{
 const li=document.createElement('li');li.className='item';li.dataset.n=o.name;
 const meta=[`in ${o.salience.in_degree}`,`out ${o.salience.out_degree}`,
   (o.roles&&o.roles.length?o.roles.join(' · '):'')].filter(Boolean).map(esc).join('</span><span>');
 li.innerHTML=`<span class="rank">${String(i+1).padStart(2,'0')}</span>`+
   `<span class="name">${esc(o.name)}</span>`+
   `<span class="cost" data-cost="${o.cost}">~${o.cost}</span>`+
   `<span class="meta"><span>${meta}</span></span>`+
   (o.description?`<span class="desc">${esc(o.description)}</span>`:'');
 stack.appendChild(li);
 // the frontier divider lives right after the last row; moved via order-index
 o._el=li;
});
const frontier=document.createElement('div');frontier.className='frontier';frontier.id='frontier';
let prevIn=new Set();
function setCode(el,name,inCtx){
 const cost=el.querySelector('.cost');
 if(inCtx){cost.textContent='~'+cost.dataset.cost;cost.classList.remove('code');}
 else{cost.innerHTML=`<span class="code">${esc(OUTSIDE[name]||'budget_exceeded')}</span>`;}
}
function render(budget){
 const{keep,approx}=replay(budget);
 let lastIn=-1;
 ORDER.forEach((o,i)=>{
  const inCtx=keep.has(o.name),el=o._el;
  el.classList.toggle('in',inCtx);el.classList.toggle('out',!inCtx);
  if(inCtx){lastIn=i;if(!prevIn.has(o.name)){el.classList.remove('cross');void el.offsetWidth;el.classList.add('cross');}}
  setCode(el,o.name,inCtx);
 });
 // slide the frontier to sit just below the last retained row
 const anchor=lastIn>=0?ORDER[lastIn]._el:null;
 if(anchor&&anchor.nextSibling!==frontier)stack.insertBefore(frontier,anchor.nextSibling);
 else if(!anchor&&stack.firstChild!==frontier)stack.insertBefore(frontier,stack.firstChild);
 frontier.dataset.tok=budget;
 prevIn=keep;
 const inN=keep.size,outN=ORDER.length-inN;
 $('#in-n').textContent=inN;$('#out-n').textContent=outN;
 $('#used').textContent=approx;$('#bud').textContent=budget;$('#bval').textContent=budget;
 const over=approx>budget&&inN>1;                 // greedy floor keeps 1 even over budget
 const v=$('#verdict');v.dataset.v=over?'UNVERIFIABLE':'MATCH';v.textContent=over?'UNVERIFIABLE':'MATCH';
}
const slider=$('#budget');
slider.addEventListener('input',()=>render(+slider.value));
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
    scope = (f"focused on <code>{html.escape(str(focus))}</code>"
             if focus else "across the whole workspace")
    root = html.escape(str(env["root"]))
    data = json.dumps(lens, separators=(",", ":"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Context Lens — {root}</title>
<style>{_CSS}</style></head><body>
<div class="wrap">
<header>
<p class="eyebrow">index · context lens</p>
<h1>What fits in the context budget
<span class="verdict" id="verdict" data-v="MATCH">MATCH</span></h1>
<p class="sub">Every repo {root} maps, ranked in the order an agent's context would
fill, {scope}. Drag the budget and the frontier slides: repos above it are <b>RETAINED</b>,
the ones below are <b>OMITTED</b> and carry their failure code. The slider replays the exact
selection <code>index context-envelope</code> emits, so what you see is what the agent gets.</p>
</header>

<div class="panel">
<div class="rail">
<div class="slider">
<label for="budget">token budget</label>
<input type="range" id="budget" min="{lo}" max="{hi}" value="{built}" step="1"
 aria-label="token budget" aria-describedby="readout">
<span class="readout" id="readout"><span class="big" id="bval">{built}</span></span>
</div>
<div class="readout"><span class="big" id="used">0</span><span class="of">/ <span id="bud">{built}</span> tokens used</span></div>
<div class="legend">
<span class="k"><span class="dot in"></span>RETAINED <b class="n" id="in-n">0</b></span>
<span class="k"><span class="dot out"></span>OMITTED <b class="n" id="out-n">0</b></span>
</div>
</div>
<ul class="stack" id="stack"></ul>
</div>

<footer>
<div><span class="lbl">receipt sha256</span> &nbsp;{html.escape(lens['receipt_sha256'])}</div>
<div><span class="lbl">re-check</span> &nbsp;{html.escape(env['recheck']['command'])} &nbsp;·&nbsp; graph-pack {html.escape(env['recheck']['graph_pack_sha256'][:16])}…</div>
</footer>
</div>
<script>const LENS={data};{_JS}</script>
</body></html>"""
