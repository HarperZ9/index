# Design: `index atlas` -- an explorable two-layer code + knowledge map

> Date: 2026-06-24
> Status: Approved in shape (brainstorming) -- pending spec review, then plan.
> Repo: PUBLIC `index` (`HarperZ9/index`, PyPI `index-graph`), worktree `c:/dev/worktrees/wrm-rename`. Builds on the v1.1 dashboard core (branch `feat/v1.1-enhancements` @ `8ca9f0e`).

## Summary

`index atlas` is the first concrete slice of a developer quality-of-life platform: one self-contained, local-first, zero-dependency dashboard where a developer opens a project and **traverses both its structure and its knowledge** as a single interconnected graph. Today `index` maps repos + dependencies; the atlas adds the project's **knowledge** -- markdown docs, READMEs, ADRs -- as first-class nodes, `[[wiki-linked]]` and clustered onto the code they describe. It is *risorgi-for-internals*: the interconnected-knowledge interaction model, turned inward for a codebase.

`atlas` is a subcommand of `index` (not a separate product). It reuses the v1.1 dashboard substrate (evidence tooltips, legend, cycle highlighting, neighborhood highlight) and is governed by three operator requirements: **easily navigable**, **rendering easily perceptible and contextualized**, and **part of `index`**.

## Global constraints

- **Zero runtime dependencies** -- pure Python 3.11+ stdlib only (incl. the markdown renderer and the pan/zoom JS).
- **Local-first, self-contained** -- one HTML file, no server, no accounts, NO external URL/CDN/`<link>`/`@import`. All dynamic HTML routes through `esc()`/`escape()`.
- **Deterministic** -- same workspace → byte-identical render (sorted nodes/edges/links).
- **Privacy** -- the public demo uses the synthetic sample only; a real workspace is never published.
- **Backward compatible** -- `atlas` is additive; `map`/`graph`/`context`/`viz` and their JSON are unchanged. The atlas pack is a superset of the context pack.
- **No regression** -- the v1.1 suite (140) stays green; the atlas adds its own tests.
- **Escaping precondition (carry-forward from the substrate review):** before extending `viz/html.py`'s `detail()` for doc content, fix its pre-existing unescaped `innerHTML` sinks (confidence, role-join, `s.line`). The atlas renders richer, more attacker-adjacent content, so the escaping invariant must hold first.

## The graph model -- three node types, four edge types

- **Nodes:** `repo` (today), `doc` (one per markdown file -- id = workspace-relative path; title = first H1 or filename), `external` (today).
- **Edges:**
  - `depends-on` -- repo→repo (index's existing dependency edges, with evidence + confidence + cycles).
  - `describes` -- doc→repo, by **location** (a `.md` inside repo X's tree describes X). A workspace-root doc that names repos `describes` each named repo.
  - `links-to` -- doc→doc / doc→repo, from **`[[wiki-links]]`** in the doc body, resolved by normalized title/filename/repo-name.
  - `mentions` -- doc→repo / doc→doc, from prose **name-mentions** of a repo or doc title; weaker, and **deduped** against `describes`/`links-to` (a mention is dropped if a stronger edge already connects the pair).

Determinism: docs sorted by path; edges sorted; `[[link]]` resolution is first-match by normalized name with a recorded ambiguity warning (mirrors the existing dependency-resolution pattern).

## Knowledge sources

Every markdown file (`.md`, `.markdown`) under the workspace minus the existing pruned dirs (`node_modules`, `.git`, `__pycache__`, …); the existing `.index.toml` prune/scan config is honored. README / `docs/` / ADRs are just markdown -- no special-casing. A `[knowledge]` config block (glob include/exclude) is a later refinement, not in this slice.

## Rendering -- perceptible + contextualized

1. **Readable docs (perceptible):** a new zero-dep **minimal markdown→HTML renderer** (`knowledge/markdown.py`) supporting a wide GFM-lite subset -- ATX headings, paragraphs, unordered/ordered lists, fenced + inline code, bold/italic, links `[t](u)`, blockquotes, pipe tables, task-list items, and **`[[wiki-links]]`** rendered as clickable spans (`<a data-atlas-target="…">`). Images render as **escaped alt-text only** (the `src` is never emitted or fetched). Every text segment is HTML-escaped; URLs are attribute-escaped; no raw HTML passthrough (so untrusted doc content can't inject). Clicking a `[[link]]` navigates the graph (no page nav).
2. **Distinct, clustered nodes (perceptible + contextualized):** `doc` nodes get a distinct shape/treatment (a "page" style -- rounded, lighter, a doc glyph) clearly different from `repo` rectangles and `external` pills. Crucially, **doc nodes are laid out clustered next to the repo they `describe`** (a sub-cluster adjacent to / beneath the repo node), so the map reads as "each repo and its knowledge," not a flat hairball. Root/cross-cutting docs sit in a dedicated knowledge band.
3. **The panel is the contextualizer:** selecting a `doc` shows its **rendered markdown** + a context header -- "**describes** `repo`", its **outgoing `[[links]]`** (clickable), and its **backlinks** ("linked from …"). Selecting a `repo` shows its shape (deps, role, cycles) + **the docs that describe it**. You always know what a node is and where it sits.

## Navigability (operator requirement: "easily navigable")

- **Pan/zoom** -- a small zero-dep SVG pan/zoom (wheel to zoom about the cursor, drag to pan, a "reset/fit" control). Essential now that the graph carries repos *and* docs. (Also closes the v1.1 "no zoom/pan" gap.)
- **Unified search** -- the existing search box matches **both** repo names and doc titles; matches highlight, non-matches dim.
- **Follow `[[links]]`** -- clickable wiki-links in rendered docs select+center the target node.
- **Focus mode** -- click-to-focus a node reduces the view to its neighborhood (reuses the v1.1 neighborhood highlight + the existing `--focus` closure); a control clears focus.
- **Navigation trail** -- a breadcrumb of visited nodes with a **Back** control, so traversal is reversible (the risorgi "follow then return" feel).

## CLI

`index atlas [--root ROOT] [--format html] [--focus NAME] [--out FILE] [--out-dir DIR] [--no-external]` -- parallel to `viz`. Builds the atlas graph (repos + docs + the four edge types) and renders the dashboard. `--format html` for this slice (svg/mermaid can follow). `map`/`graph`/`context`/`viz` untouched.

## Architecture / new units

- `knowledge/docs.py` -- discover markdown files; parse each into a `Doc` (path, title, body, `[[link]]` targets, mentioned names). Pure, deterministic.
- `knowledge/markdown.py` -- the minimal, escaping-safe markdown→HTML renderer (+ `[[link]]` → clickable span). Pure.
- `knowledge/atlas.py` -- assemble the index `DependencyGraph` + the docs into an `AtlasGraph` / atlas pack: repo nodes (from index) + doc/external nodes + the four edge types; resolves `[[links]]` + `describes` + deduped `mentions`. Emits a pack that is a **superset** of the context pack (so the existing renderers degrade gracefully).
- `viz/` extensions -- doc-node rendering + the describe-clustering layout; pan/zoom + unified search + nav-trail JS; the panel's markdown + backlinks; `[[link]]` navigation. (Fix `detail()` escaping first.)
- `cli.py` -- the `atlas` subcommand.

Each unit is independently testable: docs parsing (title/links/mentions extraction), markdown rendering (each construct + escaping + `[[link]]` spans), atlas assembly (the four edge types + dedup + determinism), and viz (doc markup, clustering, pan/zoom hooks present, panel backlinks).

## Phasing (one plan, in order; each phase ends green + reviewable)

1. **Escaping precondition** -- fix `detail()`'s unescaped sinks (the carry-forward).
2. **Knowledge ingestion** -- `knowledge/docs.py`: discover + parse markdown (title, `[[links]]`, mentions).
3. **Markdown renderer** -- `knowledge/markdown.py`: the zero-dep subset renderer + `[[link]]` spans + escaping tests.
4. **Atlas assembly** -- `knowledge/atlas.py`: the two-layer pack (nodes + four edge types + dedup + determinism).
5. **Atlas render** -- doc nodes + describe-clustering layout + the contextualizing panel (rendered markdown, describes, links, backlinks) + `[[link]]` navigation.
6. **Navigability** -- pan/zoom + unified search + focus + nav-trail.
7. **`index atlas` CLI** + a synthetic atlas demo (sample repos + sample docs with `[[links]]` and a cross-repo link) + README section.

## Error handling / risks (honest bounds)

- **Markdown renderer scope:** a *subset*, not CommonMark. Unsupported constructs degrade to escaped text, never raw HTML -- correctness (no injection) over completeness. Tested against a fixture exercising each supported construct + a hostile-content case.
- **`[[link]]` ambiguity:** first-match by normalized name + a recorded warning (same contract as dependency resolution); never crashes.
- **Layout at scale:** clustering docs per repo grows the graph; pan/zoom + focus keep it navigable, but a very large workspace may need the later `[knowledge]` glob to scope. The recursion-depth carry-forward in `find_cycles` is breadth-insensitive (depth = longest acyclic chain), so docs-as-nodes don't worsen it; noted, not addressed here.
- **Determinism with many docs:** all collections sorted; render byte-stable (a determinism test guards it).

## Success criteria

1. `index atlas --root <project> --format html` writes one self-contained HTML file showing repos AND docs as one graph, doc nodes distinct and clustered by the repo they describe.
2. Opening it: you can **pan/zoom**, **search** repos+docs, click a doc to read its **rendered markdown** with **clickable `[[links]]`** that navigate, see a doc's **describes/links/backlinks**, **focus** a neighborhood, and **step back** through a trail.
3. The four edge types are derived correctly (location→describes, `[[wiki]]`→links-to, deduped mentions) -- verified against a fixture; resolution is deterministic.
4. Zero runtime deps; self-contained (no external URLs); all doc content escaped (a hostile-doc test proves no injection); `detail()` escaping fixed.
5. The v1.1 suite stays green; the atlas adds tests for docs/markdown/atlas/viz; the render is deterministic.
6. `atlas` is an `index` subcommand; `map`/`graph`/`context`/`viz` unchanged.

## Plan 2 design deltas (resolved 2026-06-24 -- brainstorm pass)

The engine (Plan 1) is built; these resolve the open Plan-2 questions against the **real** atlas pack (`index atlas --root <ws> --json`, verified on a synthetic 2-repo / 4-doc sample exercising all four edge types). They refine -- not replace -- the design above.

1. **Doc layout -- satellites + knowledge band.** Docs that `describe` a repo render as small "page" nodes clustered immediately beside/beneath that repo, within its role layer's region; cross-cutting docs (those that describe nothing) sit in a dedicated **knowledge band** below the role layers. Placement is deterministic (sorted; no overlap with the existing role bands).
2. **Navigability -- all in Plan 2.** Pan/zoom, unified repo+doc search, focus mode, and the nav-trail/breadcrumb (Back) **all ship in Plan 2** (not split to a later plan). Plan 2 is correspondingly larger; subagent-driven-development sequences it into discrete, individually-reviewed tasks.
3. **Markdown subset -- widest GFM-lite.** ATX headings, paragraphs, ordered/unordered lists, fenced + inline code, bold/italic, `[t](u)` links, `[[wiki-links]]`, **plus blockquotes, pipe tables, and task-list items**. Images render as **escaped alt-text only** -- the `src` is never emitted or fetched (preserves self-contained + injection-safe). Every text segment escaped; no raw-HTML passthrough; unsupported constructs degrade to escaped text. The wider surface earns proportionally more escaping + determinism tests, including a hostile-content fixture per construct.
4. **`mentions` edges -- dim + toggle.** The weakest edge renders as the faintest line; a legend toggle (reusing the existing chip/filter pattern) hides/shows them. Default: visible but muted. (Rationale: in a trivial sample, `mentions` were 7 of 14 edges and partly shared-word noise -- e.g. `[[Beta]]` yields both a `links-to`→repo and a `mentions`→doc.)
5. **Render architecture -- new modules, not in-place edits.** The atlas render lives in new unit(s) that **compose** the existing `viz/layout.py` + `viz/svg.py` + `viz/html.py` primitives, leaving `viz`'s output byte-identical (its determinism + self-contained tests stay green). The exact module boundary is fixed in the plan. Precondition unchanged: fix `detail()`'s unescaped sinks (`roles.join`, `confidence`, `s.line` in `sig()`) **first**.
