"""Workbench JS part 2: map interactions, command palette, keyboard, boot."""
from __future__ import annotations

WB_JS_UX = r"""
/* ---------- map (pan/zoom/select/focus + lens overlay) ---------- */
let view={k:1,tx:0,ty:0};
function applyView(){const vp=$('#map-stage #viewport');
 if(vp)vp.setAttribute('transform',`translate(${view.tx},${view.ty}) scale(${view.k})`);}
function fitMap(){view={k:1,tx:0,ty:0};applyView();}
function svgPt(svg,cx,cy){const r=svg.getBoundingClientRect(),vb=svg.viewBox.baseVal;
 return{x:(cx-r.left)/r.width*vb.width,y:(cy-r.top)/r.height*vb.height};}
function wireMap(){const stage=$('#map-stage'),svg=stage&&stage.querySelector('svg');if(!svg)return;
 svg.removeAttribute('width');svg.removeAttribute('height');
 svg.addEventListener('wheel',ev=>{ev.preventDefault();
  const p=svgPt(svg,ev.clientX,ev.clientY),f=ev.deltaY<0?1.12:1/1.12,
   nk=Math.min(9,Math.max(.15,view.k*f));
  view.tx=p.x-(p.x-view.tx)*(nk/view.k);view.ty=p.y-(p.y-view.ty)*(nk/view.k);view.k=nk;applyView();},{passive:false});
 let drag=null;
 svg.addEventListener('pointerdown',ev=>{drag={x:ev.clientX,y:ev.clientY,tx:view.tx,ty:view.ty};
  stage.classList.add('grabbing');svg.setPointerCapture(ev.pointerId);});
 svg.addEventListener('pointermove',ev=>{if(!drag)return;
  const r=svg.getBoundingClientRect(),vb=svg.viewBox.baseVal;
  view.tx=drag.tx+(ev.clientX-drag.x)*vb.width/r.width;
  view.ty=drag.ty+(ev.clientY-drag.y)*vb.height/r.height;applyView();});
 svg.addEventListener('pointerup',()=>{drag=null;stage.classList.remove('grabbing');});
 $$('#map-stage .node').forEach(g=>{g.style.cursor='pointer';
  g.addEventListener('click',()=>select('repo',g.dataset.name));
  g.addEventListener('dblclick',()=>focusHood('repo',g.dataset.name));});
 $$('#map-stage .docnode').forEach(g=>{g.style.cursor='pointer';
  g.addEventListener('click',()=>select('doc',g.dataset.doc));});
 $('#zoom-fit').onclick=fitMap;
 $('#focus-clear').onclick=()=>{$$('#map-stage .dim').forEach(e=>e.classList.remove('dim'));};
 $('#toggle-lens-overlay').onclick=e=>{const on=e.currentTarget.getAttribute('aria-pressed')==='true';
  e.currentTarget.setAttribute('aria-pressed',String(!on));highlightMap();};
}
function focusHood(kind,id){const keep=new Set([kind+':'+id]);
 D.repos.forEach(r=>{(r.depends_on||[]).forEach(d=>{
  if(r.name===id)keep.add('repo:'+d.to);
  if(d.to===id)keep.add('repo:'+r.name);});});
 (D.knowledge_edges||[]).forEach(e=>{
  if(kind==='doc'&&e.from===id)keep.add(e.to_kind+':'+e.to);
  if(e.to===id&&e.to_kind===kind)keep.add('doc:'+e.from);});
 $$('#map-stage .node').forEach(g=>g.classList.toggle('dim',!keep.has('repo:'+g.dataset.name)));
 $$('#map-stage .docnode').forEach(g=>g.classList.toggle('dim',!keep.has('doc:'+g.dataset.doc)));
 $$('#map-stage .edge').forEach(p=>p.classList.toggle('dim',
  !(keep.has('repo:'+p.dataset.from)&&keep.has('repo:'+p.dataset.to))));
 $$('#map-stage .kedge').forEach(l=>l.classList.toggle('dim',
  !(keep.has('doc:'+l.dataset.from)&&(keep.has('repo:'+l.dataset.to)||keep.has('doc:'+l.dataset.to)))));
}
function highlightMap(keepSet){
 // lens overlay: when ON, repos outside the current budget replay get dimmed
 const btn=$('#toggle-lens-overlay');
 const on=btn&&btn.getAttribute('aria-pressed')==='true';
 const keep=keepSet||replay(S.budget).keep;
 $$('#map-stage .node').forEach(g=>{
  g.classList.toggle('lens-out',on&&!keep.has(g.dataset.name));
  g.classList.toggle('sel',!!S.sel&&S.sel.kind==='repo'&&S.sel.id===g.dataset.name);});
 $$('#map-stage .docnode').forEach(g=>
  g.classList.toggle('sel',!!S.sel&&S.sel.kind==='doc'&&S.sel.id===g.dataset.doc));
}

/* ---------- command palette (ctrl/cmd-K) ---------- */
const ACTIONS=[
 {k:'mode',t:'Go to Overview',run:()=>setMode('overview')},
 {k:'mode',t:'Go to Map',run:()=>setMode('map')},
 {k:'mode',t:'Go to Docs',run:()=>setMode('docs')},
 {k:'mode',t:'Go to Context Lens',run:()=>setMode('lens')},
 {k:'mode',t:'Go to Health',run:()=>setMode('health')},
 {k:'mode',t:'Go to Spine (flagship interop)',run:()=>setMode('spine')},
 {k:'copy',t:'Copy envelope command (basket)',run:()=>copy(envelopeCmd(),'envelope command')},
 {k:'copy',t:'Copy re-check: freshness',run:()=>copy(D.freshness.recheck,'freshness re-check')},
 {k:'copy',t:'Copy receipt sha256',run:()=>copy(D.receipt_sha256,'receipt sha256')},
];
let pIdx=0,pHits=[];
function pOpen(){$('#palette').classList.add('on');const i=$('#pinput');i.value='';pQuery('');i.focus();}
function pClose(){$('#palette').classList.remove('on');}
function fuzzy(q,s){q=q.toLowerCase();s=s.toLowerCase();let i=0;
 for(const c of s){if(c===q[i])i++;if(i===q.length)return true;}return q.length===0;}
function pQuery(q){
 const hits=[];
 ACTIONS.forEach(a=>{if(fuzzy(q,a.t))hits.push({k:a.k,t:a.t,s:'action',run:a.run});});
 D.repos.forEach(r=>{if(fuzzy(q,r.name))hits.push({k:'repo',t:r.name,
  s:(r.roles||[]).join('/')||'repo',run:()=>{select('repo',r.name);}});});
 D.docs.forEach(d=>{if(fuzzy(q,d.title)||fuzzy(q,d.id))hits.push({k:'doc',t:d.title,
  s:d.id,run:()=>{setMode('docs');select('doc',d.id);}});});
 pHits=hits.slice(0,40);pIdx=0;
 $('#presults').innerHTML=pHits.map((h,i)=>
  `<div class="pr${i===0?' sel':''}" data-i="${i}"><span class="k">${esc(h.k)}</span>`+
  `<span class="t">${esc(h.t)}</span><span class="s">${esc(h.s)}</span></div>`).join('')
  ||'<div class="pr"><span class="t">no matches</span></div>';
 $$('#presults .pr').forEach(el=>el.onclick=()=>{const h=pHits[+el.dataset.i];if(h){pClose();h.run();}});
}
function pMove(d){if(!pHits.length)return;pIdx=(pIdx+d+pHits.length)%pHits.length;
 $$('#presults .pr').forEach((el,i)=>el.classList.toggle('sel',i===pIdx));
 const el=$$('#presults .pr')[pIdx];if(el)el.scrollIntoView({block:'nearest'});}

/* ---------- keyboard ---------- */
document.addEventListener('keydown',ev=>{
 const pal=$('#palette').classList.contains('on');
 if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='k'){ev.preventDefault();pal?pClose():pOpen();return;}
 if(pal){
  if(ev.key==='Escape'){pClose();}
  else if(ev.key==='ArrowDown'){ev.preventDefault();pMove(1);}
  else if(ev.key==='ArrowUp'){ev.preventDefault();pMove(-1);}
  else if(ev.key==='Enter'){const h=pHits[pIdx];if(h){pClose();h.run();}}
  return;}
 if(ev.target.tagName==='INPUT')return;
 const m={'1':'overview','2':'map','3':'docs','4':'lens','5':'health','6':'spine'}[ev.key];
 if(m){setMode(m);return;}
 if(ev.key==='/'){ev.preventDefault();pOpen();return;}
 if(ev.key==='p'&&S.sel&&S.sel.kind==='repo'){togglePin(S.sel.id);detailRepo(S.sel.id);return;}
 if(ev.key==='Escape'){$$('#map-stage .dim').forEach(e=>e.classList.remove('dim'));}
});
$('#pinput')&&($('#pinput').oninput=e=>pQuery(e.target.value));
$('#palette').addEventListener('click',ev=>{if(ev.target.id==='palette')pClose();});

/* ---------- boot ---------- */
readHash();
$$('.mode').forEach(b=>b.onclick=()=>setMode(b.id.slice(5)));
$('#searchbtn').onclick=pOpen;
$('#basketbtn').onclick=()=>{setMode('overview');
 $('#basketbar').scrollIntoView({block:'center'});};
buildLens();renderLens();renderBasket();wireMap();
setMode(S.mode);
if(S.sel)select(S.sel.kind,S.sel.id);
"""
