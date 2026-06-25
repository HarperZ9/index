"""Atlas dashboard CSS + JS (string constants embedded into the self-contained HTML)."""
from __future__ import annotations

ATLAS_CSS = """
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-body)}
main{display:grid;grid-template-columns:1fr 360px;min-height:100vh}
#stage{overflow:hidden;padding:1rem;position:relative}#stage svg{max-width:100%;height:auto;cursor:grab}
#stage.grabbing svg{cursor:grabbing}
aside{border-left:1px solid var(--hairline);padding:1rem;font-family:var(--font-mono);font-size:.82rem;overflow:auto}
.controls{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.6rem;align-items:center}
.chip{cursor:pointer;border:1px solid var(--hairline);border-radius:6px;padding:.2em .5em;background:transparent;color:var(--ink)}
.chip[aria-pressed=true]{background:var(--accent);color:var(--bg)}
input[type=search]{flex:1;min-width:8rem;padding:.4em;background:transparent;color:var(--ink);border:1px solid var(--hairline);border-radius:6px}
#trail{font-family:var(--font-mono);font-size:.72rem;opacity:.8;margin:.2rem 0 .6rem;min-height:1.2em}
#trail a{color:var(--gold);cursor:pointer;text-decoration:underline}
#detail h3{margin:.2rem 0;color:var(--gold)}#detail h4{margin:.6rem 0 .2rem;color:var(--gold)}
#detail .md{font-family:var(--font-body);font-size:.95rem;line-height:1.5;border-top:1px solid var(--hairline);margin-top:.6rem;padding-top:.6rem}
#detail .md pre{background:rgba(0,0,0,.3);padding:.5em;overflow:auto}#detail .md table{border-collapse:collapse}
#detail .md th,#detail .md td{border:1px solid var(--hairline);padding:.2em .5em}
#detail .md .wikilink{color:var(--accent);cursor:pointer}#detail .md .md-img{opacity:.6;font-style:italic}
a.wikilink{color:var(--accent)}
@media(max-width:820px){main{grid-template-columns:1fr}aside{border-left:none}}
"""

ATLAS_JS = r"""
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>String(s).trim().toLowerCase().replace(/_/g,'-').replace(/ /g,'-');
const repos={};(DATA.repos||[]).forEach(r=>repos[r.name]=r);
const docs={};(DATA.docs||[]).forEach(d=>docs[d.id]=d);
const tgt={};                       // normalized name -> {kind,id}
(DATA.repos||[]).forEach(r=>{if(!(norm(r.name)in tgt))tgt[norm(r.name)]={kind:'repo',id:r.name};});
(DATA.docs||[]).forEach(d=>{[d.title,d.id.split('/').pop().replace(/\.[^.]+$/,'')].forEach(c=>{if(!(norm(c)in tgt))tgt[norm(c)]={kind:'doc',id:d.id};});});
function kedgesFrom(id){return (DATA.knowledge_edges||[]).filter(e=>e.from===id);}
function selectClear(){$$('.node,.docnode').forEach(n=>n.classList.remove('sel'));}
function detailRepo(name){selectClear();
 const g=$(`.node[data-name="${cssEsc(name)}"]`);if(g)g.classList.add('sel');
 const outs=(DATA.relations||[]).filter(e=>e.from===name&&!e.external);
 const descBy=(DATA.knowledge_edges||[]).filter(e=>e.type==='describes'&&e.to===name);
 $('#detail').innerHTML=`<h3>${esc(name)} <small>repo</small></h3>`+
  `<div>roles: ${esc((DATA.roles[name]||[]).join(', '))||'none'}</div>`+
  `<h4>depends on</h4>`+(outs.map(e=>`<div>${esc(e.to)} [${esc(e.confidence)}]</div>`).join('')||'none')+
  `<h4>documented by</h4>`+(descBy.map(e=>linkNode(e.from,'doc')).join('')||'none');
 pushTrail({kind:'repo',id:name});}
function detailDoc(id){selectClear();
 const g=$(`.docnode[data-doc="${cssEsc(id)}"]`);if(g)g.classList.add('sel');
 const d=docs[id]||{title:id};
 const out=kedgesFrom(id);
 const desc=out.filter(e=>e.type==='describes').map(e=>esc(e.to)).join(', ');
 const links=out.filter(e=>e.type!=='describes').map(e=>linkNode(e.to,e.to_kind)).join('')||'none';
 const back=(DATA.backlinks&&DATA.backlinks[id]||[]).map(b=>linkNode(b.from,'doc')).join('')||'none';
 $('#detail').innerHTML=`<h3>${esc(d.title)} <small>doc</small></h3>`+
  (desc?`<div>describes <b>${desc}</b></div>`:'')+
  `<h4>links</h4>${links}<h4>linked from</h4>${back}`+
  `<div class="md">${DATA.doc_html[id]||''}</div>`;
 wireWikilinks();pushTrail({kind:'doc',id});}
function linkNode(id,kind){const label=kind==='repo'?id:(docs[id]?docs[id].title:id);
 return `<div><a class="navlink" data-kind="${kind}" data-id="${esc(id)}">${esc(label)}</a></div>`;}
function cssEsc(s){return String(s).replace(/["\\]/g,'\\$&');}
function go(kind,id){kind==='repo'?detailRepo(id):detailDoc(id);
 const sel=kind==='repo'?`.node[data-name="${cssEsc(id)}"]`:`.docnode[data-doc="${cssEsc(id)}"]`;
 const el=$(sel);if(el&&el.scrollIntoView)el.scrollIntoView({block:'center',inline:'center'});}
function wireWikilinks(){$$('#detail .wikilink,#detail .navlink').forEach(a=>a.addEventListener('click',ev=>{
  ev.preventDefault();const t=a.dataset.atlasTarget?tgt[a.dataset.atlasTarget]:{kind:a.dataset.kind,id:a.dataset.id};
  if(t)go(t.kind,t.id);}));}
let trail=[];
function pushTrail(node){if(trail.length&&trail[trail.length-1].id===node.id)return;trail.push(node);renderTrail();}
function renderTrail(){$('#trail').innerHTML=trail.map((n,i)=>`<a data-i="${i}">${esc(n.id)}</a>`).join(' › ');
 $$('#trail a').forEach(a=>a.addEventListener('click',()=>{const n=trail[+a.dataset.i];trail=trail.slice(0,+a.dataset.i);go(n.kind,n.id);}));}
let view={k:1,tx:0,ty:0};
function applyView(){const vp=$('#viewport');if(vp)vp.setAttribute('transform',`translate(${view.tx},${view.ty}) scale(${view.k})`);}
function svgPt(svg,cx,cy){const r=svg.getBoundingClientRect();const vb=svg.viewBox.baseVal;
 return {x:(cx-r.left)/r.width*vb.width,y:(cy-r.top)/r.height*vb.height};}
function wireZoom(){const stage=$('#stage'),svg=stage&&stage.querySelector('svg');if(!svg)return;
 svg.addEventListener('wheel',ev=>{ev.preventDefault();const p=svgPt(svg,ev.clientX,ev.clientY);
  const f=ev.deltaY<0?1.1:1/1.1,nk=Math.min(8,Math.max(.2,view.k*f));
  view.tx=p.x-(p.x-view.tx)*(nk/view.k);view.ty=p.y-(p.y-view.ty)*(nk/view.k);view.k=nk;applyView();},{passive:false});
 let drag=null;
 svg.addEventListener('pointerdown',ev=>{drag={x:ev.clientX,y:ev.clientY,tx:view.tx,ty:view.ty};
  stage.classList.add('grabbing');svg.setPointerCapture(ev.pointerId);});
 svg.addEventListener('pointermove',ev=>{if(!drag)return;const r=svg.getBoundingClientRect(),vb=svg.viewBox.baseVal;
  view.tx=drag.tx+(ev.clientX-drag.x)*vb.width/r.width;view.ty=drag.ty+(ev.clientY-drag.y)*vb.height/r.height;applyView();});
 svg.addEventListener('pointerup',()=>{drag=null;stage.classList.remove('grabbing');});
 $('#zoom-reset').addEventListener('click',()=>{view={k:1,tx:0,ty:0};applyView();});}
function searchApply(){const q=$('#search').value.trim().toLowerCase();const on=new Set();
 $$('.node').forEach(g=>{const m=!q||g.dataset.name.toLowerCase().includes(q);
  g.classList.toggle('dim',!m);if(m)on.add('repo:'+g.dataset.name);});
 $$('.docnode').forEach(g=>{const d=docs[g.dataset.doc];
  const m=!q||g.dataset.doc.toLowerCase().includes(q)||(d&&d.title.toLowerCase().includes(q));
  g.classList.toggle('dim',!m);if(m)on.add('doc:'+g.dataset.doc);});
 $$('.edge').forEach(p=>p.classList.toggle('dim',!!q&&!(on.has('repo:'+p.dataset.from)&&on.has('repo:'+p.dataset.to))));
 $$('.kedge').forEach(l=>{const t=on.has('repo:'+l.dataset.to)||on.has('doc:'+l.dataset.to);
  l.classList.toggle('dim',!!q&&!(on.has('doc:'+l.dataset.from)&&t));});}
function wireMentions(){const b=$('#toggle-mentions');b.addEventListener('click',()=>{
  const on=b.getAttribute('aria-pressed')==='true';b.setAttribute('aria-pressed',String(!on));
  $$('.kedge-mentions').forEach(l=>{l.style.display=on?'none':'';});});}
function neighborhood(kind,id){const keep=new Set([kind+':'+id]);
 (DATA.relations||[]).forEach(e=>{if(e.external)return;
  if(kind==='repo'&&e.from===id)keep.add('repo:'+e.to);
  if(kind==='repo'&&e.to===id)keep.add('repo:'+e.from);});
 (DATA.knowledge_edges||[]).forEach(e=>{
  if(kind==='doc'&&e.from===id)keep.add(e.to_kind+':'+e.to);
  if(e.to===id&&((kind==='repo'&&e.to_kind==='repo')||(kind==='doc'&&e.to_kind==='doc')))keep.add('doc:'+e.from);});
 return keep;}
function focusOn(kind,id){const keep=neighborhood(kind,id);
 $$('.node').forEach(g=>g.classList.toggle('dim',!keep.has('repo:'+g.dataset.name)));
 $$('.docnode').forEach(g=>g.classList.toggle('dim',!keep.has('doc:'+g.dataset.doc)));
 $$('.edge').forEach(p=>p.classList.toggle('dim',!(keep.has('repo:'+p.dataset.from)&&keep.has('repo:'+p.dataset.to))));
 $$('.kedge').forEach(l=>l.classList.toggle('dim',!(keep.has('doc:'+l.dataset.from)&&(keep.has('repo:'+l.dataset.to)||keep.has('doc:'+l.dataset.to)))));}
function clearFocus(){$$('.dim').forEach(e=>e.classList.remove('dim'));}
function wire(){
 $$('.node').forEach(g=>g.addEventListener('click',()=>detailRepo(g.dataset.name)));
 $$('.docnode').forEach(g=>g.addEventListener('click',()=>detailDoc(g.dataset.doc)));
 $$('.node').forEach(g=>g.addEventListener('dblclick',()=>focusOn('repo',g.dataset.name)));
 $$('.docnode').forEach(g=>g.addEventListener('dblclick',()=>focusOn('doc',g.dataset.doc)));
 $('#focus-clear').addEventListener('click',clearFocus);
 $('#search').addEventListener('input',searchApply);
 wireMentions();
 wireZoom();
}
document.addEventListener('DOMContentLoaded',wire);
"""
