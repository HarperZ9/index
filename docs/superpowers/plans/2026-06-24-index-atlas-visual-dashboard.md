# index atlas -- Visual Dashboard (Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the atlas *engine* (`index atlas --json`, already shipped) into a self-contained, navigable HTML dashboard that renders repos **and** their markdown docs as one explorable two-layer graph.

**Architecture:** A new zero-dep Python markdown renderer (`knowledge/markdown.py`) renders each doc's body to escaping-safe HTML **server-side** at build time. New `viz/atlas_*.py` modules *compose* the existing `viz/layout.py` + `viz/svg.py` primitives (leaving `viz`'s own output byte-identical) to place doc "satellites" beneath the repo they describe, render the two-layer SVG, and assemble the dashboard shell + JS (pan/zoom, unified search, focus, nav-trail, `[[link]]` navigation). The CLI gains `index atlas --format html`.

**Tech Stack:** Python 3.11+ stdlib only (`re`, `html`, `json`, `xml.sax.saxutils`, `dataclasses`). Embedded vanilla JS + CSS (no framework, no CDN). Tests: pytest.

## Global Constraints

Every task's requirements implicitly include this section. Values copied verbatim from `docs/superpowers/specs/2026-06-24-index-atlas-design.md`.

- **Zero runtime dependencies** -- pure Python 3.11+ stdlib only (incl. the markdown renderer and the pan/zoom JS). A test (`tests/test_viz_boundary.py`) enforces that every `viz/*.py` imports **only** stdlib or `index_graph`; new `viz/atlas_*.py` modules MUST obey it.
- **Local-first, self-contained** -- one HTML file, no server, no accounts, **no external resource loads**: no `<link>`, no `@import`, no `src="http…"` / `src="//…"`, no `url(http…)`, no `<script src>`. (Clickable `<a href="https://…">` *inside rendered doc content* is permitted -- it navigates on click, it does not auto-load. The self-contained test targets resource-load vectors, not content links. See Task 7.)
- **All dynamic HTML routes through escaping** -- `xml.sax.saxutils.escape`/`quoteattr` (Python) or the JS `esc()` helper. The atlas renders **untrusted doc content**, so a hostile-doc test must prove no breakout (`doc.count("</script>") == 1`).
- **Deterministic** -- same workspace → byte-identical render. All collections sorted; no wall-clock, no `Math.random`, no host data in output. Determinism tests (`render(x) == render(x)`) guard every renderer.
- **Backward compatible** -- `atlas` stays additive; `map`/`graph`/`context`/`viz` and their JSON are unchanged. The atlas pack is a strict superset of the context pack. `viz`'s rendered output stays **byte-identical** (its determinism + boundary tests stay green).
- **No regression** -- the existing suite (153 tests) stays green; the atlas adds its own tests.
- **Commit trailer** -- every commit's last line: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Publish is operator-gated** -- do NOT push, tag, or publish. Commit to the branch only.

**Repo:** `c:/dev/worktrees/wrm-rename`, branch `feat/v1.1-enhancements` (base `357d012`). Run the full suite with: `python -m pytest tests/ --color=no -q`. The editable install means the `index` console script runs this worktree's code.

---

## File Structure

**New files:**
- `src/index_graph/knowledge/markdown.py` -- `render_markdown(text)` + `render_inline(text)`: GFM-lite → escaping-safe HTML. Pure, deterministic. (Tasks 2–4)
- `src/index_graph/viz/atlas_layout.py` -- `build_atlas_layout(pack, *, include_external)` → `AtlasLayout`: repo positions (via `build_layout`) + doc-satellite + knowledge-band placement. (Task 5)
- `src/index_graph/viz/atlas_svg.py` -- `render_atlas_svg(atlas)` → the two-layer SVG (repos+deps reuse `svg.py`; doc page-nodes + knowledge edges new). (Task 6)
- `src/index_graph/viz/atlas_assets.py` -- `ATLAS_CSS` + `ATLAS_JS` string constants (the dashboard's styles + behavior; accretes across Tasks 7–11). (Task 7)
- `src/index_graph/viz/atlas_html.py` -- `render_atlas_html(pack, docs, *, svg, include_external)` → the full dashboard document. (Task 7)
- `examples/atlas_demo.py` -- fabricates a synthetic workspace in a temp dir and renders `examples/atlas-demo.html`. (Task 14)
- Tests: `tests/test_markdown.py`, `tests/test_atlas_layout.py`, `tests/test_atlas_svg.py`, `tests/test_atlas_html.py`, `tests/test_atlas_demo.py`.

**Modified files:**
- `src/index_graph/viz/html.py:50-57` -- fix `detail()` escaping (Task 1).
- `src/index_graph/viz/__init__.py` -- export `build_atlas_layout`, `render_atlas_svg`, `render_atlas_html` (Tasks 5–7).
- `src/index_graph/cli.py:56-58,87-107` -- extend the `atlas` subparser + `_cmd_atlas` with the html path (Task 13).
- `tests/viz_fixtures.py` -- add `simple_atlas()` (pack + `Doc` list) fixture (Task 5).
- `tests/test_viz_html.py` -- add the `detail()` escaping lock test (Task 1).
- `README.md` -- atlas section (Task 14).

---

## Task 1: Fix `detail()` escaping (precondition)

`viz/html.py`'s embedded `detail()` builds panel `innerHTML` with three unescaped sinks -- the roles join, `${e.confidence}`, and `s.line` in `sig()`. The tooltip path already escapes these (commit `a1a9f50`); make `detail()` consistent **before** doc content flows through any panel.

**Files:**
- Modify: `src/index_graph/viz/html.py:50-57`
- Test: `tests/test_viz_html.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change -- `render_html` output gains `esc(...)` around the three sinks.

- [ ] **Step 1: Write the failing lock test** -- append to `tests/test_viz_html.py`:

```python
def test_detail_panel_escapes_confidence_roles_and_line():
    doc = _doc(simple_pack())
    # the three previously-unescaped sinks must now route through esc()
    assert "esc(e.confidence)" in doc
    assert "esc(s.line)" in doc
    assert "esc((DATA.roles[name]" in doc
    # and the raw unescaped interpolations must be gone
    assert "${e.confidence}" not in doc
    assert "':'+s.line:" not in doc
```

- [ ] **Step 2: Run it -- expect FAIL**

Run: `python -m pytest tests/test_viz_html.py::test_detail_panel_escapes_confidence_roles_and_line -v`
Expected: FAIL (`esc(e.confidence)` not yet present).

- [ ] **Step 3: Apply the escaping fix** -- in `src/index_graph/viz/html.py`, replace the `detail`/`sig` lines (currently 50-57):

```python
 function detail(name){const r=idx[name]||{name,ecosystems:[],markers:[]};
 const outs=DATA.relations.filter(e=>e.from===name);
 const ins=DATA.relations.filter(e=>e.to===name);
 const sig=e=>(e.signals||[]).map(s=>`${esc(s.file)}${s.line?':'+esc(s.line):''} ${esc(s.kind)}`).join('; ');
 $('#detail').innerHTML=`<h3>${esc(name)}</h3><div>roles: ${esc((DATA.roles[name]||[]).join(', '))||'--'}</div>
 <div>in ${ (DATA.salience[name]||{}).in_degree||0 } · out ${ (DATA.salience[name]||{}).out_degree||0 }</div>
 <h4>depends on</h4>${outs.map(e=>`<div>${esc(e.target_name)} [${esc(e.confidence)}] <small>${sig(e)}</small></div>`).join('')||'--'}
 <h4>depended on by</h4>${ins.map(e=>`<div>${esc(e.from)} [${esc(e.confidence)}]</div>`).join('')||'--'}`;}
```

(Three changes only: `esc(s.line)`, `esc((DATA.roles[name]||[]).join(', '))`, and `esc(e.confidence)` in both the `outs` and `ins` maps.)

- [ ] **Step 4: Run the test + the full viz_html suite -- expect PASS, no regression**

Run: `python -m pytest tests/test_viz_html.py -v`
Expected: all PASS (the new test + the pre-existing 9).

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/viz/html.py tests/test_viz_html.py
git commit -m "fix(viz): esc() detail() panel confidence, roles, and line

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Markdown renderer -- inline pass

Build the inline renderer first (block constructs in Task 3 call it). Handles: escaping, inline code, images→alt-text, `[[wiki-links]]`, `[text](url)` links (safe schemes only), bold, italic. Order matters: code spans are stashed first (their content is escaped, never re-parsed), then literal text is escaped, then constructs are substituted on the escaped text.

**Files:**
- Create: `src/index_graph/knowledge/markdown.py`
- Test: `tests/test_markdown.py`

**Interfaces:**
- Consumes: `from .docs import _norm` (the shared normalizer -- `[[wiki]]` targets must normalize identically to how `atlas.py` resolved them: space/underscore→dash, lowercased).
- Produces: `render_inline(text: str) -> str` (escaping-safe HTML fragment, no enclosing block tag).

- [ ] **Step 1: Write failing tests** -- create `tests/test_markdown.py`:

```python
from index_graph.knowledge.markdown import render_inline


def test_escapes_html_special_chars():
    assert render_inline("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_bold_and_italic():
    assert render_inline("**x** and *y*") == "<strong>x</strong> and <em>y</em>"


def test_inline_code_is_escaped_and_not_reparsed():
    assert render_inline("use `a < *b*`") == 'use <code>a &lt; *b*</code>'


def test_wikilink_becomes_atlas_target_span():
    out = render_inline("see [[Auth Design]]")
    assert '<a class="wikilink" href="#" data-atlas-target="auth-design">Auth Design</a>' in out


def test_wikilink_alias_renders_alias_text():
    out = render_inline("[[threat-model|the threats]]")
    assert 'data-atlas-target="threat-model"' in out
    assert ">the threats</a>" in out


def test_safe_link_kept_unsafe_dropped_to_text():
    assert '<a href="https://x.dev" rel="noopener noreferrer">site</a>' in render_inline("[site](https://x.dev)")
    assert render_inline("[x](javascript:alert(1))") == "x"  # unsafe scheme -> text only


def test_image_renders_alt_text_only_no_src():
    out = render_inline("![a diagram](https://evil/x.png)")
    assert out == '<span class="md-img">a diagram</span>'
    assert "evil" not in out and "http" not in out
```

- [ ] **Step 2: Run -- expect FAIL** (`ModuleNotFoundError`)

Run: `python -m pytest tests/test_markdown.py -v`
Expected: FAIL (module/function missing).

- [ ] **Step 3: Implement the inline renderer** -- create `src/index_graph/knowledge/markdown.py`:

```python
"""Zero-dependency GFM-lite markdown -> escaping-safe HTML for atlas docs."""
from __future__ import annotations

import re
from html import escape as _esc          # &<>"' -> entities (quote=True by default)

from .docs import _norm                  # shared normalizer: space/underscore -> dash, lower

_CODE = re.compile(r"`([^`]+)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_WIKILINK = re.compile(r"\[\[\s*([^\]|]+?)\s*(?:\|\s*([^\]]*?)\s*)?\]\]")
_LINK = re.compile(r"\[([^\]]+)\]\(\s*([^)\s]+)[^)]*\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
# permitted href schemes: http(s), mailto, anchors, relative paths. NOT javascript:/data:/vbscript:.
_SAFE_URL = re.compile(r"^(?:https?:|mailto:|#|/|\./|\.\./|[^:]*$)", re.I)


def _wiki_sub(m: "re.Match") -> str:
    target, alias = m.group(1), m.group(2)
    label = alias if alias else target            # already inside escaped text
    return ('<a class="wikilink" href="#" data-atlas-target="%s">%s</a>'
            % (_esc(_norm(target), quote=True), label))


def _link_sub(m: "re.Match") -> str:
    label, url = m.group(1), m.group(2)
    if not _SAFE_URL.match(url):
        return label                              # drop unsafe scheme, keep the text
    return '<a href="%s" rel="noopener noreferrer">%s</a>' % (url, label)


def render_inline(text: str) -> str:
    codes: list[str] = []

    def _stash(m: "re.Match") -> str:
        codes.append("<code>" + _esc(m.group(1)) + "</code>")
        return "\x00%d\x00" % (len(codes) - 1)    # null-byte sentinel: absent from markdown, survives escaping

    text = _CODE.sub(_stash, text)
    text = _esc(text)                             # escape all remaining literal text
    text = _IMAGE.sub(lambda m: '<span class="md-img">' + m.group(1) + "</span>", text)
    text = _WIKILINK.sub(_wiki_sub, text)
    text = _LINK.sub(_link_sub, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)
    return text
```

- [ ] **Step 4: Run -- expect PASS**

Run: `python -m pytest tests/test_markdown.py -v`
Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/knowledge/markdown.py tests/test_markdown.py
git commit -m "feat(knowledge): markdown inline renderer (escape, code, wiki, links, emphasis)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Markdown renderer -- block pass

Add the block-level renderer that calls `render_inline`: ATX headings, paragraphs, fenced code, blockquotes, unordered/ordered lists, and task-list items. (Tables come in Task 4.)

**Files:**
- Modify: `src/index_graph/knowledge/markdown.py`
- Test: `tests/test_markdown.py`

**Interfaces:**
- Consumes: `render_inline` (Task 2).
- Produces: `render_markdown(text: str) -> str` -- newline-joined HTML block elements.

- [ ] **Step 1: Write failing tests** -- append to `tests/test_markdown.py`:

```python
from index_graph.knowledge.markdown import render_markdown


def test_heading_levels():
    assert render_markdown("# A\n\n### B") == "<h1>A</h1>\n<h3>B</h3>"


def test_paragraph_joins_wrapped_lines_and_renders_inline():
    assert render_markdown("hello **world**\nsecond line") == "<p>hello <strong>world</strong> second line</p>"


def test_fenced_code_block_is_escaped_verbatim():
    md = "```\nif a < b: pass\n```"
    assert render_markdown(md) == "<pre><code>if a &lt; b: pass</code></pre>"


def test_unordered_list():
    assert render_markdown("- one\n- two") == "<ul>\n<li>one</li>\n<li>two</li>\n</ul>"


def test_ordered_list():
    assert render_markdown("1. one\n2. two") == "<ol>\n<li>one</li>\n<li>two</li>\n</ol>"


def test_task_list_items_render_checkboxes():
    out = render_markdown("- [ ] todo\n- [x] done")
    assert '<li class="task"><input type="checkbox" disabled> todo</li>' in out
    assert '<li class="task"><input type="checkbox" checked disabled> done</li>' in out


def test_blockquote():
    assert render_markdown("> quoted **b**") == "<blockquote>quoted <strong>b</strong></blockquote>"
```

- [ ] **Step 2: Run -- expect FAIL** (`render_markdown` missing)

Run: `python -m pytest tests/test_markdown.py -k "render_markdown or heading or list or blockquote or fenced or paragraph or task" -v`
Expected: FAIL.

- [ ] **Step 3: Implement the block renderer** -- append to `src/index_graph/knowledge/markdown.py`:

```python
_HEADING = re.compile(r"(#{1,6})\s+(.*)$")
_ULI = re.compile(r"\s*[-*+]\s+(.*)$")
_OLI = re.compile(r"\s*\d+[.)]\s+(.*)$")
_TASK = re.compile(r"\s*[-*+]\s+\[([ xX])\]\s+(.*)$")
_BQ = re.compile(r">\s?(.*)$")


def _starts_block(line: str) -> bool:
    return bool(_HEADING.match(line) or _ULI.match(line) or _OLI.match(line)
                or line.startswith("```") or line.startswith(">") or "|" in line)


def _render_li(text: str) -> str:
    task = _TASK.match(text)
    if task:
        checked = " checked" if task.group(1) in ("x", "X") else ""
        return ('<li class="task"><input type="checkbox"%s disabled> %s</li>'
                % (checked, render_inline(task.group(2).strip())))
    body = (_ULI.match(text) or _OLI.match(text)).group(1)
    return "<li>" + render_inline(body.strip()) + "</li>"


def _consume_list(lines: list[str], i: int) -> tuple[str, int]:
    ordered = bool(_OLI.match(lines[i]) and not _ULI.match(lines[i]))
    items: list[str] = []
    while i < len(lines) and (_ULI.match(lines[i]) or _OLI.match(lines[i])):
        items.append(_render_li(lines[i]))
        i += 1
    tag = "ol" if ordered else "ul"
    return "<%s>\n%s\n</%s>" % (tag, "\n".join(items), tag), i


def render_markdown(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("```"):
            i += 1
            buf: list[str] = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1                                    # skip the closing fence (or run off end)
            out.append("<pre><code>" + _esc("\n".join(buf)) + "</code></pre>")
            continue
        h = _HEADING.match(line)
        if h:
            lvl = len(h.group(1))
            out.append("<h%d>%s</h%d>" % (lvl, render_inline(h.group(2).strip()), lvl))
            i += 1; continue
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(_BQ.match(lines[i]).group(1)); i += 1
            out.append("<blockquote>" + render_inline(" ".join(b for b in buf if b)) + "</blockquote>")
            continue
        if _ULI.match(line) or _OLI.match(line):
            block, i = _consume_list(lines, i)
            out.append(block); continue
        if line.strip() == "":
            i += 1; continue
        buf = []
        while i < n and lines[i].strip() != "" and not _starts_block(lines[i]):
            buf.append(lines[i]); i += 1
        out.append("<p>" + render_inline(" ".join(buf)) + "</p>")
    return "\n".join(out)
```

- [ ] **Step 4: Run -- expect PASS** (whole markdown suite)

Run: `python -m pytest tests/test_markdown.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/knowledge/markdown.py tests/test_markdown.py
git commit -m "feat(knowledge): markdown block renderer (headings, lists, code, blockquote, tasks)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Markdown renderer -- tables + safety locks

Add pipe tables, then lock the renderer's two load-bearing invariants: hostile content never breaks out, and the render is deterministic.

**Files:**
- Modify: `src/index_graph/knowledge/markdown.py`
- Test: `tests/test_markdown.py`

**Interfaces:**
- Consumes: `render_inline`, `render_markdown` (Tasks 2–3).
- Produces: no new public symbol -- `render_markdown` now also handles `| a | b |` tables.

- [ ] **Step 1: Write failing tests** -- append to `tests/test_markdown.py`:

```python
def test_pipe_table():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    out = render_markdown(md)
    assert "<table>" in out and "</table>" in out
    assert "<th>A</th>" in out and "<th>B</th>" in out
    assert "<td>1</td>" in out and "<td>2</td>" in out


def test_hostile_content_is_fully_escaped_no_breakout():
    md = "# <script>alert(1)</script>\n\n`</script>` and **<img src=x onerror=y>**"
    out = render_markdown(md)
    assert "<script>" not in out          # no raw opening tag survives
    assert "</script>" not in out         # no raw closing tag survives
    assert "&lt;script&gt;" in out
    assert "onerror" in out and "<img" not in out  # the literal text is kept, but escaped


def test_render_is_deterministic():
    md = "# T\n\n- a\n- b\n\n> q\n\n| x | y |\n| - | - |\n| 1 | 2 |"
    assert render_markdown(md) == render_markdown(md)
```

- [ ] **Step 2: Run -- expect FAIL** (table not handled)

Run: `python -m pytest tests/test_markdown.py -k "table or hostile or deterministic" -v`
Expected: `test_pipe_table` FAILS.

- [ ] **Step 3: Implement tables** -- in `src/index_graph/knowledge/markdown.py`, add the helpers and wire them into `render_markdown` **before** the list/paragraph branches:

```python
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")


def _is_table(lines: list[str], i: int) -> bool:
    return ("|" in lines[i] and i + 1 < len(lines) and bool(_TABLE_SEP.match(lines[i + 1])))


def _row_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _consume_table(lines: list[str], i: int) -> tuple[str, int]:
    head = _row_cells(lines[i]); i += 2          # header row + separator row
    body: list[str] = []
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        cells = _row_cells(lines[i])
        body.append("<tr>" + "".join("<td>" + render_inline(c) + "</td>" for c in cells) + "</tr>")
        i += 1
    thead = "<tr>" + "".join("<th>" + render_inline(c) + "</th>" for c in head) + "</tr>"
    return "<table>\n<thead>%s</thead>\n<tbody>%s</tbody>\n</table>" % (thead, "\n".join(body)), i
```

Then, inside `render_markdown`'s `while` loop, add this branch **immediately before** the `if _ULI.match(line) or _OLI.match(line):` branch:

```python
        if _is_table(lines, i):
            block, i = _consume_table(lines, i)
            out.append(block); continue
```

- [ ] **Step 4: Run -- expect PASS** (whole markdown suite)

Run: `python -m pytest tests/test_markdown.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/knowledge/markdown.py tests/test_markdown.py
git commit -m "feat(knowledge): markdown pipe tables + hostile-content & determinism locks

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Atlas layout -- doc satellites + knowledge band

Compose `build_layout` (repo positions, unchanged) with deterministic placement of doc nodes: each doc that `describes` a repo stacks in a column under that repo; cross-cutting docs flow into a knowledge band beneath. Knowledge edges become straight connectors between placed node centers.

**Files:**
- Create: `src/index_graph/viz/atlas_layout.py`
- Modify: `src/index_graph/viz/__init__.py`
- Test: `tests/test_atlas_layout.py`, `tests/viz_fixtures.py`

**Interfaces:**
- Consumes: `build_layout(pack, *, include_external) -> LayoutModel` and `MARGIN` from `viz/layout.py`; the atlas pack (`pack["docs"]`, `pack["knowledge_edges"]`).
- Produces:
  - `DocNode(id, title, x, y, w, h, describes)` -- `describes` is a repo name or `None` (band).
  - `KEdge(type, frm, to, to_kind, points)` -- `points = ((x1,y1),(x2,y2))`.
  - `AtlasLayout(repo_layout, docs, kedges, width, height)`.
  - `build_atlas_layout(pack: dict, *, include_external: bool = True) -> AtlasLayout`.

- [ ] **Step 1: Add the `simple_atlas` fixture** -- append to `tests/viz_fixtures.py`:

```python
def simple_atlas():
    """2 repos (app -> lib) + 3 docs. app/README describes app, lib/README describes lib,
    docs/arch.md is cross-cutting. Exercises describes / links-to / mentions."""
    from index_graph.knowledge.docs import Doc
    pack = {
        "roles": {"app": ["entrypoint"], "lib": ["library"]},
        "relations": [_edge("app", "lib")],
        "cycles": [],
        "salience": {
            "app": {"in_degree": 0, "out_degree": 1, "hub": False},
            "lib": {"in_degree": 1, "out_degree": 0, "hub": False},
        },
        "salience_audit": [],
        "repos": [
            {"name": "app", "ecosystems": ["python"], "description": "app", "markers": ["entry"]},
            {"name": "lib", "ecosystems": ["python"], "description": "lib", "markers": ["published"]},
        ],
        "warnings": [],
        "docs": [
            {"id": "app/README.md", "title": "App", "dir": "app"},
            {"id": "docs/arch.md", "title": "Architecture", "dir": "docs"},
            {"id": "lib/README.md", "title": "Lib", "dir": "lib"},
        ],
        "knowledge_edges": [
            {"type": "describes", "from": "app/README.md", "to": "app", "to_kind": "repo"},
            {"type": "links-to", "from": "app/README.md", "to": "lib", "to_kind": "repo"},
            {"type": "links-to", "from": "docs/arch.md", "to": "app", "to_kind": "repo"},
            {"type": "describes", "from": "lib/README.md", "to": "lib", "to_kind": "repo"},
            {"type": "mentions", "from": "docs/arch.md", "to": "lib", "to_kind": "repo"},
        ],
        "knowledge_warnings": [],
    }
    docs = [
        Doc("app/README.md", "App", "# App\n\nThe app. Uses [[lib]].", ("lib",), "app"),
        Doc("docs/arch.md", "Architecture", "# Architecture\n\nApp and lib. See [[App]].", ("app",), "docs"),
        Doc("lib/README.md", "Lib", "# Lib\n\nThe library.", (), "lib"),
    ]
    return pack, docs
```

- [ ] **Step 2: Write failing tests** -- create `tests/test_atlas_layout.py`:

```python
from index_graph.viz.atlas_layout import build_atlas_layout, DocNode
from viz_fixtures import simple_atlas


def _by_id(atlas):
    return {d.id: d for d in atlas.docs}


def test_describing_doc_sits_below_its_repo():
    pack, _ = simple_atlas()
    atlas = build_atlas_layout(pack)
    d = _by_id(atlas)["app/README.md"]
    assert d.describes == "app"
    assert d.y > atlas.repo_layout.height       # in the doc region, below the repo graph


def test_cross_cutting_doc_is_a_band_node():
    pack, _ = simple_atlas()
    atlas = build_atlas_layout(pack)
    assert _by_id(atlas)["docs/arch.md"].describes is None


def test_describes_edge_connects_doc_and_repo():
    pack, _ = simple_atlas()
    atlas = build_atlas_layout(pack)
    kinds = {(k.type, k.frm, k.to) for k in atlas.kedges}
    assert ("describes", "app/README.md", "app") in kinds


def test_no_two_doc_nodes_overlap():
    pack, _ = simple_atlas()
    atlas = build_atlas_layout(pack)
    boxes = [(d.x, d.y, d.x + d.w, d.y + d.h) for d in atlas.docs]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax0, ay0, ax1, ay1 = boxes[i]
            bx0, by0, bx1, by1 = boxes[j]
            assert ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0, "doc nodes overlap"


def test_layout_is_deterministic():
    pack, _ = simple_atlas()
    a, b = build_atlas_layout(pack), build_atlas_layout(pack)
    assert [vars(d) for d in a.docs] == [vars(d) for d in b.docs]
    assert a.width == b.width and a.height == b.height
```

- [ ] **Step 3: Run -- expect FAIL** (`ModuleNotFoundError`)

Run: `python -m pytest tests/test_atlas_layout.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement the atlas layout** -- create `src/index_graph/viz/atlas_layout.py`:

```python
"""Two-layer atlas layout: repo positions (reused) + doc satellites + knowledge band."""
from __future__ import annotations

from dataclasses import dataclass

from .layout import build_layout, LayoutModel, MARGIN

_DOC_W, _DOC_H, _ROW_GAP, _COL_GAP = 160.0, 30.0, 10.0, 24.0


@dataclass(frozen=True)
class DocNode:
    id: str
    title: str
    x: float
    y: float
    w: float
    h: float
    describes: str | None          # repo name, or None for a band (cross-cutting) doc


@dataclass(frozen=True)
class KEdge:
    type: str                      # describes | links-to | mentions
    frm: str
    to: str
    to_kind: str                   # repo | doc
    points: tuple[tuple[float, float], tuple[float, float]]


@dataclass(frozen=True)
class AtlasLayout:
    repo_layout: LayoutModel
    docs: tuple[DocNode, ...]
    kedges: tuple[KEdge, ...]
    width: float
    height: float


def build_atlas_layout(pack: dict, *, include_external: bool = True) -> AtlasLayout:
    repo_layout = build_layout(pack, include_external=include_external)
    repo_by_name = {n.name: n for n in repo_layout.nodes}

    # describes target per doc (first by sorted edge order wins -> deterministic)
    describes: dict[str, str] = {}
    for e in sorted(pack.get("knowledge_edges", []), key=lambda e: (e["from"], e["type"], e["to_kind"], e["to"])):
        if e["type"] == "describes" and e["from"] not in describes:
            describes[e["from"]] = e["to"]

    docs_meta = sorted(pack.get("docs", []), key=lambda d: d["id"])
    region_top = repo_layout.height + 50.0
    placed: dict[str, DocNode] = {}

    # described docs -> one column per repo, columns flow left-to-right without overlapping
    by_repo: dict[str, list[dict]] = {}
    for d in docs_meta:
        target = describes.get(d["id"])
        if target in repo_by_name:
            by_repo.setdefault(target, []).append(d)
    cursor_x = MARGIN
    col_depth = 0
    for repo in sorted(by_repo, key=lambda r: (repo_by_name[r].x, r)):
        x = max(repo_by_name[repo].x, cursor_x)        # under its repo, never overlapping the prior column
        for k, d in enumerate(by_repo[repo]):
            y = region_top + k * (_DOC_H + _ROW_GAP)
            placed[d["id"]] = DocNode(d["id"], d["title"], x, y, _DOC_W, _DOC_H, repo)
        cursor_x = x + _DOC_W + _COL_GAP
        col_depth = max(col_depth, len(by_repo[repo]))

    # band docs (describe nothing / unknown repo) -> a wrapping row beneath the columns
    band_top = region_top + max(col_depth, 1) * (_DOC_H + _ROW_GAP) + 40.0
    width_guess = max(repo_layout.width, cursor_x)
    bx = MARGIN
    for d in docs_meta:
        if d["id"] in placed:
            continue
        if bx > MARGIN and bx + _DOC_W + MARGIN > width_guess:
            bx = MARGIN
            band_top += _DOC_H + _ROW_GAP
        placed[d["id"]] = DocNode(d["id"], d["title"], bx, band_top, _DOC_W, _DOC_H, None)
        bx += _DOC_W + _COL_GAP

    docs = tuple(placed[d["id"]] for d in docs_meta)

    def _center(node_id: str, kind: str):
        if kind == "repo" and node_id in repo_by_name:
            r = repo_by_name[node_id]
            return (r.x + r.w / 2.0, r.y + r.h / 2.0)
        if node_id in placed:
            d = placed[node_id]
            return (d.x + d.w / 2.0, d.y + d.h / 2.0)
        return None

    kedges: list[KEdge] = []
    for e in sorted(pack.get("knowledge_edges", []), key=lambda e: (e["from"], e["type"], e["to_kind"], e["to"])):
        a = _center(e["from"], "doc")
        b = _center(e["to"], e["to_kind"])
        if a is not None and b is not None:
            kedges.append(KEdge(e["type"], e["from"], e["to"], e["to_kind"], (a, b)))

    width = max([d.x + d.w for d in docs] + [repo_layout.width]) + MARGIN
    height = max([d.y + d.h for d in docs] + [repo_layout.height]) + MARGIN
    return AtlasLayout(repo_layout, docs, tuple(kedges), width, height)
```

- [ ] **Step 5: Export it** -- in `src/index_graph/viz/__init__.py`, add the import and `__all__` entry:

```python
from .atlas_layout import build_atlas_layout
```
and add `"build_atlas_layout"` to `__all__`.

- [ ] **Step 6: Run -- expect PASS**

Run: `python -m pytest tests/test_atlas_layout.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/index_graph/viz/atlas_layout.py src/index_graph/viz/__init__.py tests/test_atlas_layout.py tests/viz_fixtures.py
git commit -m "feat(viz): atlas layout -- doc satellites + knowledge band + edge connectors

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Atlas SVG -- two-layer render

Render the `AtlasLayout` to one self-contained SVG: repos + dependency edges reuse `svg.py`'s helpers (so they stay identical to `viz`); doc page-nodes and knowledge-edge connectors are new. The transformable content is wrapped in `<g id="viewport">` (Task 8's pan/zoom target). `mentions` edges get the dimmest class.

**Files:**
- Create: `src/index_graph/viz/atlas_svg.py`
- Modify: `src/index_graph/viz/__init__.py`
- Test: `tests/test_atlas_svg.py`

**Interfaces:**
- Consumes: `AtlasLayout`, `DocNode`, `KEdge` (Task 5); `_node_svg`, `_edge_svg` from `viz/svg.py`; `THEME`, `svg_style` from `viz/theme.py`.
- Produces: `render_atlas_svg(atlas: AtlasLayout) -> str`.

- [ ] **Step 1: Write failing tests** -- create `tests/test_atlas_svg.py`:

```python
import xml.dom.minidom as minidom

from index_graph.viz.atlas_layout import build_atlas_layout
from index_graph.viz.atlas_svg import render_atlas_svg
from viz_fixtures import simple_atlas


def _svg():
    pack, _ = simple_atlas()
    return render_atlas_svg(build_atlas_layout(pack))


def test_svg_is_well_formed_and_has_viewport():
    svg = _svg()
    minidom.parseString(svg)
    assert svg.lstrip().startswith("<svg")
    assert '<g id="viewport">' in svg


def test_repo_and_doc_nodes_present():
    svg = _svg()
    assert 'data-name="app"' in svg and 'data-name="lib"' in svg     # repos (reused renderer)
    assert 'data-doc="app/README.md"' in svg                          # doc node
    assert 'class="docnode' in svg


def test_knowledge_edge_classes_present_and_mentions_is_dim():
    svg = _svg()
    assert "kedge-describes" in svg
    assert "kedge-links-to" in svg
    assert "kedge-mentions" in svg
    assert ".kedge-mentions{" in svg and "opacity:.35" in svg          # mentions dimmest in style


def test_hostile_doc_title_stays_well_formed():
    pack, _ = simple_atlas()
    pack["docs"].append({"id": "x.md", "title": 'a"<&b', "dir": ""})
    svg = render_atlas_svg(build_atlas_layout(pack))
    minidom.parseString(svg)                                          # must not raise


def test_render_is_deterministic():
    assert _svg() == _svg()
```

- [ ] **Step 2: Run -- expect FAIL**

Run: `python -m pytest tests/test_atlas_svg.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the atlas SVG** -- create `src/index_graph/viz/atlas_svg.py`:

```python
"""Render an AtlasLayout to a self-contained two-layer SVG (repos + docs)."""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from .atlas_layout import AtlasLayout, DocNode, KEdge
from .svg import _node_svg, _edge_svg          # reuse repo node + dependency edge renderers
from .theme import THEME, svg_style


def _atlas_style() -> str:
    t = THEME
    return (
        f".docnode rect{{fill:{t.bg};stroke:{t.gold};stroke-dasharray:3 2;}}"
        f".docnode text{{font-family:{t.font_mono};fill:{t.ink};font-size:11px;}}"
        f".docnode.band rect{{stroke:{t.teal};}}"
        f".docnode.sel rect{{stroke:{t.accent};stroke-width:2;stroke-dasharray:none;}}"
        f".kedge{{fill:none;stroke-width:1;}}"
        f".kedge-describes{{stroke:{t.gold};}}"
        f".kedge-links-to{{stroke:{t.ok};stroke-dasharray:4 3;}}"
        f".kedge-mentions{{stroke:{t.muted};stroke-dasharray:1 4;opacity:.35;}}"
        f".kedge.dim,.node.dim,.docnode.dim,.edge.dim{{opacity:.08;}}"
    )


def _doc_svg(d: DocNode) -> str:
    cls = "docnode" + ("" if d.describes is not None else " band")
    return (
        f"<g class={quoteattr(cls)} data-doc={quoteattr(d.id)} data-title={quoteattr(d.title)} "
        f'tabindex="0" role="img" aria-label={quoteattr(d.title + " (doc)")}>'
        f'<rect x="{d.x:.2f}" y="{d.y:.2f}" width="{d.w:.2f}" height="{d.h:.2f}" rx="3"/>'
        f'<text x="{d.x + 8:.2f}" y="{d.y + d.h / 2 + 4:.2f}">{escape(d.title)}</text></g>'
    )


def _kedge_svg(k: KEdge) -> str:
    (a, b) = k.points
    cls = "kedge kedge-" + k.type
    return (
        f"<line class={quoteattr(cls)} data-ktype={quoteattr(k.type)} "
        f"data-from={quoteattr(k.frm)} data-to={quoteattr(k.to)} "
        f'x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}"/>'
    )


def render_atlas_svg(atlas: AtlasLayout) -> str:
    rl = atlas.repo_layout
    defs = (
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{THEME.muted}"/></marker></defs>'
    )
    style = f"<style>{svg_style()}{_atlas_style()}</style>"
    kedges = "".join(_kedge_svg(k) for k in atlas.kedges)
    repo_edges = "".join(_edge_svg(e) for e in rl.edges)
    repo_nodes = "".join(_node_svg(n) for n in rl.nodes)
    doc_nodes = "".join(_doc_svg(d) for d in atlas.docs)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {atlas.width:.2f} {atlas.height:.2f}" '
        f'width="{atlas.width:.2f}" height="{atlas.height:.2f}">'
        f'{defs}{style}<g id="viewport">{kedges}{repo_edges}{repo_nodes}{doc_nodes}</g></svg>'
    )
```

- [ ] **Step 4: Export it** -- in `src/index_graph/viz/__init__.py`, add `from .atlas_svg import render_atlas_svg` and `"render_atlas_svg"` to `__all__`.

- [ ] **Step 5: Run -- expect PASS; also confirm `viz` SVG unchanged**

Run: `python -m pytest tests/test_atlas_svg.py tests/test_viz_svg.py tests/test_viz_boundary.py -v`
Expected: all PASS (the boundary test confirms `atlas_svg.py` imports only stdlib + `index_graph`).

- [ ] **Step 6: Commit**

```bash
git add src/index_graph/viz/atlas_svg.py src/index_graph/viz/__init__.py tests/test_atlas_svg.py
git commit -m "feat(viz): atlas SVG -- doc page-nodes + knowledge connectors, viewport group

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Atlas dashboard -- shell, panel, `[[link]]` navigation

Assemble the full document: the SVG, a contextualizing panel (selecting a doc shows its **server-rendered markdown** + describes/links/backlinks; selecting a repo shows deps + describing docs), and base JS for selection + `[[wiki-link]]` navigation. The embedded `DATA` JSON gets the `<`→`<` treatment so rendered doc HTML can't break the `<script>`.

**Files:**
- Create: `src/index_graph/viz/atlas_assets.py`, `src/index_graph/viz/atlas_html.py`
- Modify: `src/index_graph/viz/__init__.py`
- Test: `tests/test_atlas_html.py`

**Interfaces:**
- Consumes: `render_markdown` (Tasks 2–4); `css_variables` from `viz/theme.py`; the atlas pack + the `Doc` list (for bodies); a pre-rendered `svg` string.
- Produces:
  - `atlas_assets.ATLAS_CSS: str`, `atlas_assets.ATLAS_JS: str`.
  - `render_atlas_html(pack: dict, docs: list, *, svg: str, include_external: bool = True) -> str`.

- [ ] **Step 1: Write failing tests** -- create `tests/test_atlas_html.py`:

```python
import re

from index_graph.knowledge.docs import Doc
from index_graph.viz.atlas_layout import build_atlas_layout
from index_graph.viz.atlas_svg import render_atlas_svg
from index_graph.viz.atlas_html import render_atlas_html
from viz_fixtures import simple_atlas


def _doc(pack, docs):
    svg = render_atlas_svg(build_atlas_layout(pack))
    return render_atlas_html(pack, docs, svg=svg)


def test_is_a_complete_self_contained_document():
    doc = _doc(*simple_atlas())
    assert doc.lstrip().lower().startswith("<!doctype html>")
    assert "</html>" in doc and "const DATA =" in doc and "<svg" in doc


def test_no_external_resource_loads():
    # content links (<a href="http">) are allowed; resource-load vectors are not.
    doc = _doc(*simple_atlas())
    assert "<link" not in doc.lower()
    assert "@import" not in doc
    assert "cdn" not in doc.lower()
    assert re.search(r'src\s*=\s*["\']?(?:https?:)?//', doc) is None
    assert re.search(r'url\(\s*["\']?https?:', doc) is None
    assert "<script src" not in doc.lower()


def test_doc_markdown_is_rendered_into_data():
    doc = _doc(*simple_atlas())
    assert "doc_html" in doc
    # rendered HTML lives inside DATA, where '<' is <-escaped against script-breakout,
    # so assert on markers that survive that escaping:
    assert "data-atlas-target" in doc                 # app/README's [[lib]] became a wiki span (server-rendered)
    assert "\\u003ch1>App" in doc                      # the rendered <h1>App</h1>, '<' escaped to <


def test_backlinks_index_present():
    doc = _doc(*simple_atlas())
    assert "backlinks" in doc


def test_hostile_doc_body_cannot_break_out():
    pack, _ = simple_atlas()
    hostile = [
        Doc("app/README.md", "App", "# Pwn\n\n<script>alert(1)</script> and `</script>`", (), "app"),
        Doc("docs/arch.md", "Architecture", "x", (), "docs"),
        Doc("lib/README.md", "Lib", "y", (), "lib"),
    ]
    doc = render_atlas_html(pack, hostile, svg=render_atlas_svg(build_atlas_layout(pack)))
    assert doc.count("</script>") == 1                 # only the real closing tag


def test_wikilink_navigation_is_wired():
    doc = _doc(*simple_atlas())
    assert "data-atlas-target" in doc
    assert "function detailDoc" in doc
    assert "wikilink" in doc


def test_render_is_deterministic():
    assert _doc(*simple_atlas()) == _doc(*simple_atlas())
```

- [ ] **Step 2: Run -- expect FAIL**

Run: `python -m pytest tests/test_atlas_html.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Create the assets** -- create `src/index_graph/viz/atlas_assets.py`:

```python
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
  `<div>roles: ${esc((DATA.roles[name]||[]).join(', '))||'--'}</div>`+
  `<h4>depends on</h4>`+(outs.map(e=>`<div>${esc(e.to)} [${esc(e.confidence)}]</div>`).join('')||'--')+
  `<h4>documented by</h4>`+(descBy.map(e=>linkNode(e.from,'doc')).join('')||'--');
 pushTrail({kind:'repo',id:name});}
function detailDoc(id){selectClear();
 const g=$(`.docnode[data-doc="${cssEsc(id)}"]`);if(g)g.classList.add('sel');
 const d=docs[id]||{title:id};
 const out=kedgesFrom(id);
 const desc=out.filter(e=>e.type==='describes').map(e=>esc(e.to)).join(', ');
 const links=out.filter(e=>e.type!=='describes').map(e=>linkNode(e.to,e.to_kind)).join('')||'--';
 const back=(DATA.backlinks&&DATA.backlinks[id]||[]).map(b=>linkNode(b.from,'doc')).join('')||'--';
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
function wire(){
 $$('.node').forEach(g=>g.addEventListener('click',()=>detailRepo(g.dataset.name)));
 $$('.docnode').forEach(g=>g.addEventListener('click',()=>detailDoc(g.dataset.doc)));
}
document.addEventListener('DOMContentLoaded',wire);
"""
```

- [ ] **Step 4: Create the renderer** -- create `src/index_graph/viz/atlas_html.py`:

```python
"""Assemble the self-contained atlas dashboard document."""
from __future__ import annotations

import json

from ..knowledge.markdown import render_markdown
from .theme import css_variables
from .atlas_assets import ATLAS_CSS, ATLAS_JS


def _backlinks(pack: dict) -> dict:
    out: dict[str, list] = {}
    for e in sorted(pack.get("knowledge_edges", []), key=lambda e: (e["to"], e["from"], e["type"])):
        out.setdefault(e["to"], []).append({"from": e["from"], "type": e["type"]})
    return out


def render_atlas_html(pack: dict, docs: list, *, svg: str, include_external: bool = True) -> str:
    rendered = {d.rel_path: render_markdown(d.body) for d in sorted(docs, key=lambda d: d.rel_path)}
    data = dict(pack)
    data["doc_html"] = rendered
    data["backlinks"] = _backlinks(pack)
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>index · atlas</title>"
        f"<style>{css_variables()}{ATLAS_CSS}</style></head><body>"
        '<main><section id="stage">'
        '<div class="controls">'
        '<input type="search" id="search" placeholder="search repos + docs…" aria-label="search">'
        '<button class="chip" id="zoom-reset">reset view</button>'
        '<button class="chip" id="focus-clear">clear focus</button>'
        '<button class="chip" id="toggle-mentions" aria-pressed="true">mentions</button>'
        "</div>"
        '<div id="trail"></div>'
        f"{svg}</section>"
        '<aside><div id="detail">Select a node.</div></aside></main>'
        f"<script>const DATA = {blob};{ATLAS_JS}</script>"
        "</body></html>"
    )
```

- [ ] **Step 5: Export it** -- in `src/index_graph/viz/__init__.py`, add `from .atlas_html import render_atlas_html` and `"render_atlas_html"` to `__all__`.

- [ ] **Step 6: Run -- expect PASS** (atlas html + boundary)

Run: `python -m pytest tests/test_atlas_html.py tests/test_viz_boundary.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/index_graph/viz/atlas_assets.py src/index_graph/viz/atlas_html.py src/index_graph/viz/__init__.py tests/test_atlas_html.py
git commit -m "feat(viz): atlas dashboard -- panel with rendered markdown, backlinks, [[link]] nav

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Navigability -- pan/zoom

Wheel-zoom about the cursor + drag-to-pan over the `<g id="viewport">`, with a reset control. All JS additions go into `ATLAS_JS` in `viz/atlas_assets.py`; no Python render change (so determinism holds).

**Files:**
- Modify: `src/index_graph/viz/atlas_assets.py` (ATLAS_JS)
- Test: `tests/test_atlas_html.py`

**Interfaces:**
- Consumes: the `#viewport` group + `#stage`/`#zoom-reset` elements from Task 7.
- Produces: in-browser pan/zoom; no signature change.

- [ ] **Step 1: Write the failing wiring test** -- append to `tests/test_atlas_html.py`:

```python
def test_pan_zoom_is_wired():
    doc = _doc(*simple_atlas())
    assert "function applyView" in doc
    assert "#viewport" in doc
    assert "zoom-reset" in doc
    assert "wheel" in doc and "pointerdown" in doc
```

- [ ] **Step 2: Run -- expect FAIL**

Run: `python -m pytest tests/test_atlas_html.py::test_pan_zoom_is_wired -v`
Expected: FAIL.

- [ ] **Step 3: Add pan/zoom JS** -- in `src/index_graph/viz/atlas_assets.py`, insert this block into `ATLAS_JS` **immediately before** the line `function wire(){`:

```javascript
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
```

Then add `wireZoom();` inside the `wire()` function body (after the existing node/docnode wiring).

- [ ] **Step 4: Run -- expect PASS (no determinism regression)**

Run: `python -m pytest tests/test_atlas_html.py -v`
Expected: all PASS (incl. `test_render_is_deterministic`).

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/viz/atlas_assets.py tests/test_atlas_html.py
git commit -m "feat(viz): atlas pan/zoom -- wheel-zoom about cursor + drag-pan + reset

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Navigability -- unified search + mentions toggle

The search box matches **both** repo names and doc titles (dimming non-matches and their edges). The legend `mentions` chip hides/shows the dimmest edge class.

**Files:**
- Modify: `src/index_graph/viz/atlas_assets.py` (ATLAS_JS)
- Test: `tests/test_atlas_html.py`

**Interfaces:**
- Consumes: `#search`, `#toggle-mentions`, the `.node/.docnode/.edge/.kedge` markup + their `data-*`.
- Produces: in-browser unified search + mentions visibility toggle.

- [ ] **Step 1: Write the failing test** -- append to `tests/test_atlas_html.py`:

```python
def test_search_and_mentions_toggle_wired():
    doc = _doc(*simple_atlas())
    assert "function searchApply" in doc
    assert "function wireMentions" in doc
    assert "toggle-mentions" in doc
```

- [ ] **Step 2: Run -- expect FAIL**

Run: `python -m pytest tests/test_atlas_html.py::test_search_and_mentions_toggle_wired -v`
Expected: FAIL.

- [ ] **Step 3: Add search + toggle JS** -- in `src/index_graph/viz/atlas_assets.py`, insert into `ATLAS_JS` **immediately before** `function wire(){`:

```javascript
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
```

Then add `$('#search').addEventListener('input',searchApply);` and `wireMentions();` inside `wire()`.

- [ ] **Step 4: Run -- expect PASS**

Run: `python -m pytest tests/test_atlas_html.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/viz/atlas_assets.py tests/test_atlas_html.py
git commit -m "feat(viz): atlas unified repo+doc search + mentions visibility toggle

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Navigability -- focus mode

Double-clicking a node reduces the view to its neighborhood (dependency neighbors for repos; knowledge-edge neighbors for docs); `clear focus` restores. The nav-trail breadcrumb (built in Task 7) already provides reversible step-back, so no separate Back control is needed -- this task verifies it is present and adds focus.

**Files:**
- Modify: `src/index_graph/viz/atlas_assets.py` (ATLAS_JS)
- Test: `tests/test_atlas_html.py`

**Interfaces:**
- Consumes: `DATA.relations`, `DATA.knowledge_edges`, the node markup, `#focus-clear`, `#trail`.
- Produces: in-browser focus/neighborhood reduction.

- [ ] **Step 1: Write the failing test** -- append to `tests/test_atlas_html.py`:

```python
def test_focus_and_trail_wired():
    doc = _doc(*simple_atlas())
    assert "function focusOn" in doc
    assert "function neighborhood" in doc
    assert "focus-clear" in doc
    assert "function renderTrail" in doc      # nav-trail breadcrumb (reversible step-back)
```

- [ ] **Step 2: Run -- expect FAIL**

Run: `python -m pytest tests/test_atlas_html.py::test_focus_and_trail_wired -v`
Expected: FAIL (`focusOn` missing; `renderTrail` already present from Task 7).

- [ ] **Step 3: Add focus JS** -- in `src/index_graph/viz/atlas_assets.py`, insert into `ATLAS_JS` **immediately before** `function wire(){`:

```javascript
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
```

Then, inside `wire()`, add focus wiring:

```javascript
 $$('.node').forEach(g=>g.addEventListener('dblclick',()=>focusOn('repo',g.dataset.name)));
 $$('.docnode').forEach(g=>g.addEventListener('dblclick',()=>focusOn('doc',g.dataset.doc)));
 $('#focus-clear').addEventListener('click',clearFocus);
```

- [ ] **Step 4: Run -- expect PASS**

Run: `python -m pytest tests/test_atlas_html.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/index_graph/viz/atlas_assets.py tests/test_atlas_html.py
git commit -m "feat(viz): atlas focus mode -- neighborhood reduction + clear

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: CLI -- `index atlas --format html`

Extend the `atlas` subcommand to render the dashboard. Keep `--json` (engine pack, shipped + tested) byte-for-byte unchanged. Add `--format html`, `--out`, `--no-external`.

> **Scope note:** `--focus` / `--out-dir` from the spec's CLI line are **deferred** -- the in-browser focus mode (Task 10) is the richer focus story, and a single `--out` file covers the demo. Record this as a one-line deviation when updating the spec/handoff.

**Files:**
- Modify: `src/index_graph/cli.py:56-58` (subparser) and `:87-107` (`_cmd_atlas`)
- Test: `tests/test_atlas_cli.py`

**Interfaces:**
- Consumes: `viz.build_atlas_layout`, `viz.render_atlas_svg`, `viz.render_atlas_html`; `discover_docs`, `build_atlas_pack`, `build_graph`, `_repo_paths`.
- Produces: `index atlas --format html [--out FILE] [--no-external]`.

- [ ] **Step 1: Write failing tests** -- create `tests/test_atlas_cli.py`:

```python
import json
from pathlib import Path

from index_graph.cli import main


def _workspace(root: Path):
    (root / "alpha").mkdir(); (root / "beta").mkdir(); (root / "docs").mkdir()
    (root / "alpha" / ".git").write_text("", encoding="utf-8")
    (root / "alpha" / "pyproject.toml").write_text('[project]\nname="alpha"\ndependencies=["beta"]\n', encoding="utf-8")
    (root / "alpha" / "a.py").write_text("import beta\n", encoding="utf-8")
    (root / "alpha" / "README.md").write_text("# Alpha\n\nUses [[Beta]].\n", encoding="utf-8")
    (root / "beta" / ".git").write_text("", encoding="utf-8")
    (root / "beta" / "pyproject.toml").write_text('[project]\nname="beta"\n', encoding="utf-8")
    (root / "docs" / "arch.md").write_text("# Architecture\n\nalpha and beta.\n", encoding="utf-8")


def test_atlas_html_writes_self_contained_two_layer_file(tmp_path):
    _workspace(tmp_path)
    out = tmp_path / "atlas.html"
    rc = main(["atlas", "--root", str(tmp_path), "--format", "html", "--out", str(out)])
    assert rc == 0
    html = out.read_text(encoding="utf-8")
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'data-name="alpha"' in html and 'data-doc="alpha/README.md"' in html
    assert "<link" not in html.lower() and "@import" not in html


def test_atlas_json_still_emits_engine_pack(tmp_path, capsys):
    _workspace(tmp_path)
    rc = main(["atlas", "--root", str(tmp_path), "--json"])
    assert rc == 0
    pack = json.loads(capsys.readouterr().out)
    assert "knowledge_edges" in pack and "docs" in pack
```

- [ ] **Step 2: Run -- expect FAIL**

Run: `python -m pytest tests/test_atlas_cli.py -v`
Expected: FAIL (`--format` unknown / not wired).

- [ ] **Step 3: Extend the subparser** -- in `src/index_graph/cli.py`, replace the `atlas` subparser block (currently lines 56-58):

```python
    a = sub.add_parser("atlas", help="Two-layer code + knowledge map (repos + docs).")
    a.add_argument("--root", type=Path, default=Path.cwd())
    a.add_argument("--json", action="store_true")
    a.add_argument("--format", choices=["html"], default=None)
    a.add_argument("--out", default=None)
    a.add_argument("--no-external", action="store_true")
    return parser
```

- [ ] **Step 4: Wire the html path** -- in `src/index_graph/cli.py`, replace the last block of `_cmd_atlas` -- from `graph = build_graph(repo_paths)` through the final `return 0` (currently lines 100-107) -- with:

```python
    graph = build_graph(repo_paths)
    docs = discover_docs(root)
    pack = build_atlas_pack(graph, docs, repo_dirs)
    if args.format == "html":
        from . import viz
        include_external = not args.no_external
        svg = viz.render_atlas_svg(viz.build_atlas_layout(pack, include_external=include_external))
        html = viz.render_atlas_html(pack, docs, svg=svg, include_external=include_external)
        if args.out:
            Path(args.out).write_text(html, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(html)
        return 0
    if args.json:
        print(json.dumps(pack, indent=2))
    else:
        print(f"repos={len(pack['repos'])} docs={len(pack['docs'])} "
              f"knowledge_edges={len(pack['knowledge_edges'])}")
    return 0
```

(The `discover_docs` import already exists at the top of `_cmd_atlas`; the function now computes `pack` once and branches on output format.)

- [ ] **Step 5: Run -- expect PASS; confirm no CLI regression**

Run: `python -m pytest tests/test_atlas_cli.py tests/test_cli_subcommands.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/index_graph/cli.py tests/test_atlas_cli.py
git commit -m "feat(cli): index atlas --format html renders the dashboard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Synthetic demo + README

A committed, path-independent demo (`examples/atlas_demo.py` → `examples/atlas-demo.html`) plus a README section. The demo fabricates a 2-repo + 4-doc workspace in a temp dir exercising all four edge types, tables, blockquotes, and cross-repo `[[links]]`.

**Files:**
- Create: `examples/atlas_demo.py`, `examples/atlas-demo.html` (generated artifact)
- Modify: `README.md`
- Test: `tests/test_atlas_demo.py`

**Interfaces:**
- Consumes: the full pipeline (`build_graph`, `discover_docs`, `build_atlas_pack`, `viz.*`).
- Produces: `atlas_demo.build_workspace(root)`, `atlas_demo.render(root) -> str`, `atlas_demo.main()`.

- [ ] **Step 1: Write the failing smoke tests** -- create `tests/test_atlas_demo.py`:

```python
import importlib.util
import re
import tempfile
import xml.dom.minidom as minidom
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "atlas_demo", Path(__file__).resolve().parents[1] / "examples" / "atlas_demo.py")
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)


def test_demo_renders_self_contained_two_layer_html():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); demo.build_workspace(root); html = demo.render(root)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'data-name="api"' in html and 'data-name="storage"' in html
    assert 'data-doc="docs/architecture.md"' in html
    assert "kedge-describes" in html
    assert "<link" not in html.lower() and "@import" not in html
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg is not None
    minidom.parseString(svg.group(0))


def test_demo_is_path_independent_deterministic():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        ra = Path(a); demo.build_workspace(ra); ha = demo.render(ra)
        rb = Path(b); demo.build_workspace(rb); hb = demo.render(rb)
    assert ha == hb
```

- [ ] **Step 2: Run -- expect FAIL**

Run: `python -m pytest tests/test_atlas_demo.py -v`
Expected: FAIL (`examples/atlas_demo.py` missing).

- [ ] **Step 3: Create the demo script** -- create `examples/atlas_demo.py`:

```python
"""Fabricate a synthetic repos+docs workspace and render the atlas demo HTML.

Run:  python examples/atlas_demo.py   ->  writes examples/atlas-demo.html
Path-independent + deterministic (uses repo names + workspace-relative doc paths only).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from index_graph import viz
from index_graph.config import load_config
from index_graph.graph.build import build_graph
from index_graph.knowledge.atlas import build_atlas_pack
from index_graph.knowledge.docs import discover_docs
from index_graph.scan import discover_repos


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def build_workspace(root: Path) -> None:
    _w(root / "storage" / ".git", "")
    _w(root / "storage" / "pyproject.toml", '[project]\nname = "storage"\nversion = "0.1.0"\n')
    _w(root / "storage" / "storage.py", "def get(k):\n    return k\n")
    _w(root / "storage" / "README.md", "# Storage\n\nDurable key-value core. See [[Architecture]].\n")
    _w(root / "api" / ".git", "")
    _w(root / "api" / "pyproject.toml", '[project]\nname = "api"\nversion = "0.1.0"\ndependencies = ["storage"]\n')
    _w(root / "api" / "api.py", "import storage\n")
    _w(root / "api" / "README.md", "# API\n\nHTTP surface over [[Storage]].\n\n- follows the [[Architecture]]\n- [x] auth\n- [ ] rate limits\n")
    _w(root / "docs" / "architecture.md",
       "# Architecture\n\n## Overview\n\n`api` is the entry; `storage` is the core. See [[API]] and [[Storage]].\n\n"
       "> Rule: api never imports a peer API.\n")
    _w(root / "docs" / "adr-001-storage.md",
       "# ADR 001: Storage\n\n| option | verdict |\n| --- | --- |\n| sqlite | chosen |\n| flat files | rejected |\n")


def render(root: Path) -> str:
    root = root.resolve()
    config = load_config(None, root)
    repo_paths = {p.name: p for p in discover_repos(root, config)}
    repo_dirs = {}
    for name, p in repo_paths.items():
        rel = p.resolve().relative_to(root).as_posix()
        repo_dirs[name] = "" if rel == "." else rel
    docs = discover_docs(root)
    pack = build_atlas_pack(build_graph(repo_paths), docs, repo_dirs)
    svg = viz.render_atlas_svg(viz.build_atlas_layout(pack))
    return viz.render_atlas_html(pack, docs, svg=svg)


def main() -> None:
    out = Path(__file__).resolve().parent / "atlas-demo.html"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_workspace(root)
        html = render(root)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run -- expect PASS**

Run: `python -m pytest tests/test_atlas_demo.py -v`
Expected: both PASS.

- [ ] **Step 5: Generate the committed demo artifact**

Run: `python examples/atlas_demo.py`
Expected: `wrote …/examples/atlas-demo.html (… bytes)`.

- [ ] **Step 6: Add the README section** -- append to `README.md` (after the `viz` section):

```markdown
## `index atlas` -- code + knowledge map

`index atlas` renders a **two-layer** map: your repositories *and* their markdown
docs (READMEs, ADRs, design notes) as one explorable graph. Docs are first-class
nodes, `[[wiki-linked]]` and clustered onto the code they describe.

```bash
index atlas --root /path/to/workspace --format html --out atlas.html
```

Open `atlas.html` (one self-contained file, zero dependencies, no network): pan/zoom
the graph, search repos + docs, click a doc to read its rendered markdown with
clickable `[[links]]`, and double-click a node to focus its neighborhood. Edge types:
`describes` (doc→repo by location), `links-to` (`[[wiki]]`), and `mentions` (prose,
dimmest -- toggle in the legend). `index atlas --json` emits the underlying pack.

See `examples/atlas-demo.html` for a rendered sample (`python examples/atlas_demo.py`).
```

- [ ] **Step 7: Commit**

```bash
git add examples/atlas_demo.py examples/atlas-demo.html README.md tests/test_atlas_demo.py
git commit -m "feat(examples): synthetic atlas demo + README section

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after Task 12)

- [ ] **Full suite green:** `python -m pytest tests/ --color=no -q` -- expect the prior 153 + all atlas-dashboard tests passing, zero failures.
- [ ] **Boundary intact:** `python -m pytest tests/test_viz_boundary.py -v` -- every `viz/*.py` (incl. the new `atlas_*.py`) imports only stdlib + `index_graph`.
- [ ] **`viz` unchanged:** `python -m pytest tests/test_viz_svg.py tests/test_viz_html.py -v` -- the existing `viz` render is byte-identical (Task 1's escaping fix is the only intended change).
- [ ] **Manual smoke:** open `examples/atlas-demo.html` in a browser; confirm pan/zoom, search, a doc's rendered markdown with a working `[[link]]`, focus, and the mentions toggle.
- [ ] **Whole-branch review:** dispatch the opus final-review per the handoff cadence before declaring Plan 2 done. Publish stays operator-gated (no push/tag).

