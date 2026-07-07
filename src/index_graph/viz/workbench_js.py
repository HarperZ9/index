"""Workbench JS part 1: state, routing, detail panel, basket, lens replay.

Everything renders from the sealed DATA pack; every visual state is a replay
of real numbers (lens costs, evidence lines, fingerprints). URL hash carries
the full UI state (mode/selection/budget/basket) so any view is deep-linkable
and restorable offline.
"""
from __future__ import annotations

WB_JS_CORE = r"""
const D=DATA,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const REPO={};D.repos.forEach(r=>REPO[r.name]=r);
const DOC={};D.docs.forEach(d=>DOC[d.id]=d);
const ORDER=D.lens.replay.order,BASE=D.lens.replay.base_tokens;
const COST={};ORDER.forEach(o=>COST[o.name]=o.cost);
// backlinks are a projection of knowledge_edges — rebuilt here instead of
// shipped twice (a 6MB saving on large workspaces)
const BL={};(D.knowledge_edges||[]).forEach(e=>{
 (BL[e.to]=BL[e.to]||[]).push({from:e.from,type:e.type});});
const S={mode:'overview',sel:null,budget:D.lens.budget.token_budget,basket:[],trail:[]};

/* ---------- hash state (deep-linkable, offline) ---------- */
function writeHash(){
 const h='#m='+S.mode+(S.sel?'&s='+encodeURIComponent(S.sel.kind+':'+S.sel.id):'')
  +'&b='+S.budget+(S.basket.length?'&k='+S.basket.map(encodeURIComponent).join(','):'');
 if(location.hash!==h)history.replaceState(null,'',h);
}
function readHash(){
 const q=new URLSearchParams(location.hash.slice(1).replace(/&/g,'&'));
 const m=q.get('m');if(m&&$('#mode-'+m))S.mode=m;
 const b=parseInt(q.get('b'),10);if(b>0)S.budget=b;
 const k=q.get('k');if(k)S.basket=k.split(',').map(decodeURIComponent).filter(n=>REPO[n]);
 const s=q.get('s');if(s){const i=s.indexOf(':');const kind=s.slice(0,i),id=decodeURIComponent(s.slice(i+1));
  if((kind==='repo'&&REPO[id])||(kind==='doc'&&DOC[id]))S.sel={kind,id};}
}

/* ---------- toast ---------- */
let toastT=null;
function toast(msg){const t=$('#toast');t.textContent=msg;t.classList.add('on');
 clearTimeout(toastT);toastT=setTimeout(()=>t.classList.remove('on'),2600);}
function copy(text,label){
 (navigator.clipboard?navigator.clipboard.writeText(text):Promise.reject())
  .then(()=>toast('copied: '+label)).catch(()=>toast(text));
}

/* ---------- modes ---------- */
function setMode(m){S.mode=m;
 $$('.mode').forEach(b=>b.setAttribute('aria-pressed',String(b.id==='mode-'+m)));
 $$('.view').forEach(v=>v.classList.toggle('on',v.id==='view-'+m));
 if(m==='map')fitMap();
 writeHash();
}

/* ---------- selection + detail panel ---------- */
function pushTrail(sel){const last=S.trail[S.trail.length-1];
 if(!last||last.id!==sel.id)S.trail.push(sel);
 $('#crumbs').innerHTML=S.trail.slice(-6).map((n,i)=>`<a data-i="${S.trail.length-6+i<0?i:S.trail.length-Math.min(6,S.trail.length)+i}">${esc(n.id.split('/').pop())}</a>`).join(' › ');
 $$('#crumbs a').forEach(a=>a.onclick=()=>{const n=S.trail[+a.dataset.i];if(n)select(n.kind,n.id);});
}
function select(kind,id){S.sel={kind,id};pushTrail(S.sel);
 if(kind==='repo')detailRepo(id);else detailDoc(id);
 highlightMap();writeHash();
}
function evLine(e){
 return `<div class="ev">${esc(e.kind)} · ${esc(e.file)}${e.line?':'+e.line:''}</div>`;
}
function detailRepo(name){const r=REPO[name];if(!r)return;
 const inB=S.basket.includes(name);
 const deps=(r.depends_on||[]).map(d=>`<div class="dep"><span class="to navlink" data-kind="repo" data-id="${esc(d.to)}">${esc(d.to)}</span>`+
   `<span class="conf">${esc(d.confidence)}</span>${d.in_cycle?'<span class="cyc">cycle</span>':''}`+
   (d.evidence||[]).map(evLine).join('')+`</div>`).join('')||'<div class="mt">none</div>';
 const docs=(r.documented_by||[]).map(id=>`<div><a class="navlink" data-kind="doc" data-id="${esc(id)}">${esc((DOC[id]||{title:id}).title)}</a></div>`).join('')||'<div class="mt">none</div>';
 const back=(BL[name]||[]).map(b=>`<div><a class="navlink" data-kind="doc" data-id="${esc(b.from)}">${esc((DOC[b.from]||{title:b.from}).title)}</a> <span class="mt">${esc(b.type)}</span></div>`).join('')||'<div class="mt">none</div>';
 $('#detail').innerHTML=`<h3>${esc(name)} <small>repo</small></h3>`+
  `<div class="kv"><span>roles <b>${esc((r.roles||[]).join(', ')||'none')}</b></span>`+
  `<span>in <b>${r.in_degree}</b></span><span>out <b>${r.out_degree}</b></span>`+
  `<span>~<b>${COST[name]||'?'}</b> tok</span></div>`+
  (r.description?`<p>${esc(r.description)}</p>`:'')+
  `<div class="pinrow"><button class="pin" id="pinbtn" aria-pressed="${inB}">${inB?'in basket ✓':'add to context basket'}</button></div>`+
  `<h4>depends on</h4>${deps}<h4>documented by</h4>${docs}<h4>linked from</h4>${back}`+
  `<h4>freshness fingerprint</h4><div class="fp">${esc(r.fingerprint||'n/a')}</div>`;
 $('#pinbtn').onclick=()=>{togglePin(name);detailRepo(name);};
 wireNav();
}
function detailDoc(id){const d=DOC[id];if(!d)return;
 const back=(BL[id]||[]).map(b=>`<div><a class="navlink" data-kind="doc" data-id="${esc(b.from)}">${esc((DOC[b.from]||{title:b.from}).title)}</a></div>`).join('')||'<div class="mt">none</div>';
 const body=D.doc_html[id]||('<em>body not embedded (page-weight budget: '+
  D.doc_meta.bodies_embedded+' of '+D.doc_meta.total+' bodies). Open the file at <code>'+
  esc(id)+'</code> or rebuild with --max-doc-bodies.</em>');
 $('#detail').innerHTML=`<h3>${esc(d.title)} <small>doc</small></h3>`+
  `<div class="kv"><span class="mt">${esc(id)}</span></div>`+
  `<h4>linked from</h4>${back}`+
  `<div class="md">${body}</div>`;
 wireNav();
}
function wireNav(){$$('#detail .navlink,#detail .wikilink').forEach(a=>a.onclick=ev=>{
 ev.preventDefault();
 if(a.dataset.atlasTarget){const t=resolveWiki(a.dataset.atlasTarget);if(t)select(t.kind,t.id);return;}
 select(a.dataset.kind,a.dataset.id);});}
const norm=s=>String(s).trim().toLowerCase().replace(/_/g,'-').replace(/ /g,'-');
const WIKI={};D.repos.forEach(r=>{WIKI[norm(r.name)]={kind:'repo',id:r.name};});
D.docs.forEach(d=>{[d.title,d.id.split('/').pop().replace(/\.[^.]+$/,'')]
 .forEach(c=>{if(!(norm(c)in WIKI))WIKI[norm(c)]={kind:'doc',id:d.id};});});
function resolveWiki(t){return WIKI[norm(t)];}

/* ---------- context basket ---------- */
function togglePin(name){const i=S.basket.indexOf(name);
 if(i>=0)S.basket.splice(i,1);else S.basket.push(name);
 renderBasket();writeHash();
}
function basketTokens(){return S.basket.reduce((a,n)=>a+(COST[n]||0),BASE);}
function envelopeCmd(){
 return 'index context-envelope --root . --budget '+Math.max(basketTokens(),1)
  +(S.basket.length===1?' --focus '+S.basket[0]:'')+' --json';
}
function renderBasket(){
 $('#basket-n').textContent=S.basket.length;
 $('#basketbtn').dataset.n=S.basket.length;
 const bar=$('#basketbar');
 if(!S.basket.length){bar.innerHTML='<span class="bl">context basket</span>'+
  '<div class="sum">Pin repos from the detail panel (or press <b>p</b>) to assemble a working set; the exact envelope command is generated for you.</div>';return;}
 bar.innerHTML=`<span class="bl">context basket</span>`+
  `<div class="items">${S.basket.map(n=>`<button class="bitem" data-n="${esc(n)}" title="remove">${esc(n)}</button>`).join('')}</div>`+
  `<div class="sum">~<b>${basketTokens()}</b> tokens incl. base ${BASE} · ${S.basket.length} repos</div>`+
  `<button class="cta" id="copy-env">copy envelope command</button>`;
 $$('#basketbar .bitem').forEach(b=>b.onclick=()=>{togglePin(b.dataset.n);
  if(S.sel&&S.sel.kind==='repo')detailRepo(S.sel.id);});
 $('#copy-env').onclick=()=>copy(envelopeCmd(),'envelope command');
}

/* ---------- lens (budget replay — mirrors context/lens.py) ---------- */
function replay(budget){const keep=new Set();let approx=BASE;
 for(const o of ORDER){if(approx+o.cost<=budget||keep.size===0){keep.add(o.name);approx+=o.cost;}}
 return{keep,approx};}
function renderLens(){
 const{keep,approx}=replay(S.budget);
 let lastIn=-1;
 ORDER.forEach((o,i)=>{const el=o._el;if(!el)return;
  const inC=keep.has(o.name);el.classList.toggle('in',inC);el.classList.toggle('out',!inC);
  if(inC)lastIn=i;
  el.querySelector('.cost').innerHTML=inC?('~'+o.cost):'<span class="code">budget_exceeded</span>';});
 const fr=$('#frontier'),stack=$('#lens-stack');
 const anchor=lastIn>=0?ORDER[lastIn]._el:null;
 if(anchor&&anchor.nextSibling!==fr)stack.insertBefore(fr,anchor.nextSibling);
 $('#lens-used').textContent=approx;$('#lens-bval').textContent=S.budget;
 const v=keep.size<ORDER.length?'UNVERIFIABLE':'MATCH';   // mirrors replay_verdict
 const chip=$('#lens-verdict');chip.textContent=v;chip.className='verdictchip '+v;
 highlightMap(keep);
}
function buildLens(){
 const stack=$('#lens-stack');
 ORDER.forEach((o,i)=>{const li=document.createElement('div');li.className='item';
  li.innerHTML=`<span class="rank">${String(i+1).padStart(2,'0')}</span>`+
   `<span class="nm" data-kind="repo" data-id="${esc(o.name)}">${esc(o.name)}</span>`+
   `<span class="cost">~${o.cost}</span>`;
  li.querySelector('.nm').onclick=()=>select('repo',o.name);
  stack.appendChild(li);o._el=li;});
 const fr=document.createElement('div');fr.className='frontier';fr.id='frontier';stack.appendChild(fr);
 const sl=$('#lens-slider');sl.value=S.budget;
 sl.oninput=()=>{S.budget=+sl.value;renderLens();writeHash();};
}
"""
