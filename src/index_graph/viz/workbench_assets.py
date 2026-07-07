"""Workbench CSS (string constant embedded into the self-contained HTML)."""
from __future__ import annotations

WB_CSS = """
:root{
 --bg:#f4f3ef;--panel:#fbfaf7;--ink:#0b0c0e;--soft:#2f3238;--muted:#565a62;
 --hair:rgba(11,12,14,.12);--hair2:rgba(11,12,14,.07);
 --iris:#4636e8;--iris-wash:rgba(70,54,232,.08);--iris-line:rgba(70,54,232,.35);
 --warn:#8a5a12;--ok:#1f6b45;
 --mono:ui-monospace,SFMono-Regular,Consolas,"SF Mono",monospace;
 --body:Arial,Helvetica,"Helvetica Neue",sans-serif;
 --e:cubic-bezier(.22,1,.36,1);
 --z-drop:10;--z-palette:40;--z-toast:50}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);
 font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;overflow:hidden}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
.app{display:grid;grid-template-rows:auto 1fr;height:100vh}

.top{display:flex;align-items:center;gap:.9rem;padding:.6rem 1rem;
 border-bottom:1px solid var(--hair);background:var(--panel)}
.brand{font:600 .8rem/1 var(--mono);letter-spacing:.12em;color:var(--iris);
 text-transform:uppercase;white-space:nowrap}
.modes{display:flex;gap:.15rem;background:var(--hair2);border-radius:8px;padding:.18rem}
.mode{font:600 .74rem/1 var(--mono);letter-spacing:.03em;padding:.42em .8em;border-radius:6px;
 color:var(--muted);transition:color .15s,background .15s}
.mode[aria-pressed=true]{background:var(--panel);color:var(--ink);
 box-shadow:0 1px 2px rgba(11,12,14,.12)}
.mode:focus-visible{outline:2px solid var(--iris);outline-offset:2px}
.searchbtn{display:flex;align-items:center;gap:.6rem;margin-left:auto;
 font:.78rem var(--mono);color:var(--muted);border:1px solid var(--hair);
 border-radius:8px;padding:.42em .7em;min-width:14rem;justify-content:space-between}
.searchbtn kbd{font:600 .68rem var(--mono);border:1px solid var(--hair);
 border-radius:4px;padding:.1em .4em;background:var(--hair2)}
.basketbtn{position:relative;font:600 .74rem var(--mono);border:1px solid var(--hair);
 border-radius:8px;padding:.45em .8em;transition:border-color .15s}
.basketbtn[data-n]:not([data-n="0"]){border-color:var(--iris-line);color:var(--iris)}
.basketbtn .n{font-variant-numeric:tabular-nums}

.main{display:grid;grid-template-columns:1fr 380px;min-height:0}
.stage{overflow:auto;position:relative;min-width:0}
.stage:focus-visible{outline:2px solid var(--iris);outline-offset:-2px}
.view{display:none;padding:1.1rem 1.3rem}
.view.on{display:block}
#view-map.on{display:block;padding:0;height:100%;overflow:hidden}
#map-stage{height:100%;overflow:hidden;position:relative}
#map-stage svg{cursor:grab;display:block;width:100%;height:100%}
#map-stage.grabbing svg{cursor:grabbing}
.maptools{position:absolute;top:.7rem;left:.9rem;display:flex;gap:.4rem;z-index:var(--z-drop)}
.maptools .chip,.chip{font:600 .72rem var(--mono);border:1px solid var(--hair);
 background:var(--panel);border-radius:6px;padding:.32em .6em;color:var(--soft)}
.chip[aria-pressed=true]{background:var(--iris);border-color:var(--iris);color:#fff}
.legendbar{position:absolute;bottom:.7rem;left:.9rem;display:flex;gap:.9rem;z-index:var(--z-drop);
 font:600 .68rem var(--mono);color:var(--muted);background:var(--panel);
 border:1px solid var(--hair);border-radius:6px;padding:.35em .7em}
.lg{display:inline-flex;align-items:center;gap:.35em}
.lg i{width:.65em;height:.65em;border-radius:2px;display:inline-block}

aside{border-left:1px solid var(--hair);background:var(--panel);overflow:auto;
 padding:1rem 1.1rem;font-size:.88rem}
aside h3{font:600 1.05rem/1.2 var(--body);margin:.1rem 0 .1rem;letter-spacing:-.01em;
 display:flex;align-items:baseline;gap:.5rem;flex-wrap:wrap}
aside h3 small{font:600 .66rem var(--mono);color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
aside h4{font:600 .7rem var(--mono);letter-spacing:.08em;text-transform:uppercase;
 color:var(--muted);margin:1rem 0 .35rem}
.pinrow{margin:.4rem 0 .2rem}
.pin{font:600 .72rem var(--mono);border:1px solid var(--hair);border-radius:6px;
 padding:.3em .65em;transition:all .15s}
.pin[aria-pressed=true]{background:var(--iris);border-color:var(--iris);color:#fff}
.kv{font:.76rem var(--mono);color:var(--soft);display:flex;gap:.9rem;flex-wrap:wrap;margin:.2rem 0}
.kv b{color:var(--ink);font-variant-numeric:tabular-nums}
.dep{border:1px solid var(--hair2);border-radius:8px;padding:.4rem .55rem;margin:.3rem 0}
.dep .to{font:600 .85rem var(--body)}
.dep .conf{font:.68rem var(--mono);color:var(--muted);margin-left:.4em}
.dep .cyc{font:600 .66rem var(--mono);color:var(--warn);margin-left:.4em}
.ev{font:.72rem var(--mono);color:var(--muted);margin-top:.15rem}
.ev a,.navlink{color:var(--iris);cursor:pointer;text-decoration:none}
.navlink:hover,.ev a:hover{text-decoration:underline}
.fp{font:.7rem var(--mono);color:var(--muted);word-break:break-all}
.md{font-size:.9rem;line-height:1.55;border-top:1px solid var(--hair2);margin-top:.7rem;padding-top:.7rem}
.md pre{background:var(--hair2);border-radius:6px;padding:.6em;overflow:auto;font-size:.8rem}
.md table{border-collapse:collapse}.md th,.md td{border:1px solid var(--hair);padding:.25em .55em}
.md .wikilink{color:var(--iris);cursor:pointer}
.md img{max-width:100%}
.crumbs{font:.7rem var(--mono);color:var(--muted);margin-bottom:.5rem;min-height:1.1em}
.crumbs a{color:var(--iris);cursor:pointer}

.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.8rem;margin:.9rem 0}
.stat{border:1px solid var(--hair);border-radius:10px;padding:.7rem .85rem;background:var(--panel)}
.stat .n{font:600 1.5rem/1.1 var(--mono);color:var(--ink);font-variant-numeric:tabular-nums}
.stat .l{font:600 .68rem var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.stat.iris .n{color:var(--iris)}
.hero{max-width:72ch}
.hero h2{font:600 1.5rem/1.2 var(--body);letter-spacing:-.02em;margin:.2rem 0 .4rem;text-wrap:balance}
.hero p{color:var(--soft);margin:.3rem 0}
.hero code{font:.85em var(--mono);background:var(--hair2);padding:.06em .35em;border-radius:4px}
.rowlist{list-style:none;margin:.4rem 0;padding:0}
.rowlist li{display:flex;align-items:baseline;gap:.7rem;padding:.5rem .6rem;border-radius:8px;
 border:1px solid transparent}
.rowlist li:hover,.rowlist li.cursor{background:var(--iris-wash);border-color:var(--iris-line)}
.rowlist .nm{font-weight:600;cursor:pointer}
.rowlist .mt{font:.72rem var(--mono);color:var(--muted)}
.verdictchip{font:600 .66rem var(--mono);letter-spacing:.05em;padding:.25em .55em;
 border-radius:999px;border:1px solid}
.verdictchip.UNVERIFIABLE{color:var(--warn);border-color:rgba(138,90,18,.4)}
.verdictchip.MATCH{color:var(--ok);border-color:rgba(31,107,69,.4)}
.warnrow{font:.78rem var(--mono);color:var(--warn);padding:.2rem 0}
.cycchip{display:inline-block;font:600 .72rem var(--mono);color:var(--warn);
 border:1px solid rgba(138,90,18,.4);border-radius:6px;padding:.25em .6em;margin:.15rem .25rem .15rem 0}

.palette{position:fixed;inset:0;z-index:var(--z-palette);display:none;
 background:rgba(11,12,14,.28);backdrop-filter:blur(2px)}
.palette.on{display:block}
.pbox{max-width:620px;margin:9vh auto 0;background:var(--panel);border:1px solid var(--hair);
 border-radius:12px;box-shadow:0 24px 60px -24px rgba(11,12,14,.5);overflow:hidden}
.pbox input{width:100%;border:none;outline:none;background:transparent;color:var(--ink);
 font:1rem var(--body);padding:.9rem 1.1rem;border-bottom:1px solid var(--hair2)}
.presults{max-height:46vh;overflow:auto;padding:.35rem}
.pr{display:flex;align-items:baseline;gap:.7rem;padding:.5rem .75rem;border-radius:8px;cursor:pointer}
.pr.sel{background:var(--iris-wash)}
.pr .k{font:600 .62rem var(--mono);letter-spacing:.06em;text-transform:uppercase;
 color:var(--muted);min-width:3.6rem}
.pr .t{font-weight:600}
.pr .s{font:.72rem var(--mono);color:var(--muted);margin-left:auto;white-space:nowrap}
.phint{font:.68rem var(--mono);color:var(--muted);padding:.5rem .9rem;border-top:1px solid var(--hair2);
 display:flex;gap:1rem;flex-wrap:wrap}
.phint kbd{border:1px solid var(--hair);border-radius:4px;padding:.05em .35em;background:var(--hair2)}

.toast{position:fixed;bottom:1.2rem;left:50%;transform:translate(-50%,.6rem);opacity:0;
 z-index:var(--z-toast);background:var(--ink);color:var(--bg);font:600 .78rem var(--mono);
 border-radius:8px;padding:.6em 1em;transition:opacity .2s var(--e),transform .2s var(--e);
 pointer-events:none;max-width:90vw;word-break:break-all}
.toast.on{opacity:1;transform:translate(-50%,0)}

.basketbar{border:1px solid var(--iris-line);background:var(--iris-wash);border-radius:10px;
 padding:.6rem .8rem;margin:.7rem 0}
.basketbar .bl{font:600 .7rem var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--iris)}
.basketbar .items{display:flex;gap:.35rem;flex-wrap:wrap;margin:.4rem 0}
.bitem{font:600 .72rem var(--mono);background:var(--panel);border:1px solid var(--iris-line);
 border-radius:6px;padding:.25em .55em;cursor:pointer}
.bitem:hover{text-decoration:line-through}
.basketbar .sum{font:.76rem var(--mono);color:var(--soft)}
.basketbar .sum b{font-variant-numeric:tabular-nums}
.cta{font:600 .74rem var(--mono);background:var(--iris);color:#fff;border-radius:7px;
 padding:.45em .8em;margin-top:.35rem}
.cta:focus-visible{outline:2px solid var(--ink);outline-offset:2px}

/* lens view reuses the stack look */
.lensrail{display:flex;align-items:center;gap:1rem;margin:.6rem 0 .9rem;flex-wrap:wrap}
.lensrail label{font:600 .74rem var(--mono);color:var(--muted);white-space:nowrap}
.lensrail input[type=range]{flex:1;min-width:12rem;accent-color:var(--iris)}
.lensrail .big{font:600 1.25rem var(--mono);color:var(--iris);font-variant-numeric:tabular-nums}
.item{display:grid;grid-template-columns:1.7rem 1fr auto;gap:.15rem .8rem;padding:.5rem .6rem;
 position:relative;border-radius:8px;transition:background .22s var(--e),opacity .22s var(--e)}
.item::before{content:"";position:absolute;left:0;top:6px;bottom:6px;width:3px;border-radius:2px;
 background:var(--iris);transform:scaleY(0);transition:transform .22s var(--e)}
.item.in::before{transform:scaleY(1)}
.item.in{background:var(--iris-wash)}
.item.out{opacity:.6}
.item .rank{font:600 .7rem var(--mono);color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.item .nm{font-weight:600;cursor:pointer}
.item .cost{font:600 .78rem var(--mono);text-align:right;font-variant-numeric:tabular-nums}
.item .code{color:var(--warn);font-weight:600;font-size:.74rem}
.frontier{height:0;border-top:1.5px dashed var(--iris-line);margin:.1rem .3rem;position:relative;
 transition:all .25s var(--e)}
.frontier::after{content:"frontier";position:absolute;right:0;top:-.62rem;font:600 .6rem var(--mono);
 color:var(--iris);background:var(--panel);border:1px solid var(--iris-line);
 border-radius:999px;padding:.15em .5em}

footer.receipt{padding:.5rem 1rem;border-top:1px solid var(--hair);
 font:.68rem var(--mono);color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media(max-width:900px){.main{grid-template-columns:1fr}aside{display:none}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""
