# index

> Every codebase has a shape. Past a handful of repos, that shape lives only in someone's head, and they are usually busy or already gone. `index` draws it for you: how your repositories depend on each other, and the docs that explain why, as one map you can open. Built from evidence, not guesses. Zero dependencies.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![version](https://img.shields.io/badge/version-1.1-informational.svg)
[![CI](https://github.com/HarperZ9/index-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/index-graph/actions/workflows/ci.yml)
![deps: none](https://img.shields.io/badge/deps-none-success.svg)

Point `index` at a folder of Git repositories and it answers the question that gets harder with every repo you add. How does all of this actually fit together? It reads the dependencies the way your code already states them, an import in one file, a manifest line in another, and it records each edge with the file and line that proves it. Then `index atlas` does the part most tools skip. It pulls your markdown into the same picture, the READMEs, the ADRs, the design notes, so the explanation finally sits next to the thing it explains. What comes back is a single HTML file. No server, no build step, no account. Nothing to install but Python.

---

## Why

A program's structure is knowledge, and knowledge that lives in one person's memory is fragile. People take holidays. They switch teams. They leave. The next person rebuilds the map by grepping around, and gets it a little wrong. Meanwhile the documents that hold the reasons, why this service exists, why that dependency is allowed, sit in folders nobody opens, cut off from the code they describe.

`index` turns that map into something you can hold. It is deterministic, it regenerates on demand, and it is honest about where every line came from. People tend to reach for it in a few situations.

- You inherited a workspace you didn't write. Twenty repos, no diagram, the author long gone. One command gives you something to read on your first day.
- You run a monorepo, or a product spread across many repos. You want the dependency lanes at a glance, a cycle caught before it bites, and the doc for a service without digging through ten folders to find it.
- You maintain a lot of open source. The repos and the docs that explain them, kept as one map that regenerates the same way every time, so it never quietly drifts from the truth.
- You're writing onboarding. Hand someone a file that works offline, forever, and explains itself.

---

## 30-second quickstart

```bash
pip install index-graph

# the two-layer code and knowledge map (the headline):
index atlas --root /path/to/your/workspace --format html --out atlas.html
open atlas.html        # macOS and Linux, or: start atlas.html on Windows

# or just the repo dependency graph:
index viz --root /path/to/your/workspace --format html --out graph.html
```

Each command writes one HTML file. Open it in any browser, offline. Nothing to host, and nothing phones home.

---

## `index atlas`, the two-layer map

Most dependency tools stop at the code. But code is only half of what you need to understand a system. The other half is the prose that explains it, and that prose is usually stranded somewhere the graph can't see. `index atlas` brings it back in. Every markdown file becomes a node, joined to the code it documents, and you can read it without ever leaving the map.

```mermaid
flowchart TD
    subgraph code["code: repos and dependencies"]
        api["api"]
        storage["storage"]
    end
    subgraph knowledge["knowledge: your markdown docs"]
        apiR["api/README.md"]
        storageR["storage/README.md"]
        arch["docs/architecture.md"]
        adr["docs/adr-001-storage.md"]
    end
    api -- depends on --> storage
    apiR -. describes .-> api
    storageR -. describes .-> storage
    apiR -. links-to .-> arch
    apiR -. links-to .-> storage
    arch -. links-to .-> api
    arch -. mentions .-> storage
```

There are four kinds of edge on the map, and the tool derives every one of them from something real. None are guessed.

| Edge | Means | Comes from |
|------|-------|------------|
| **depends-on** | repo to repo | a real import and manifest dependency, with the file:line that witnesses it |
| **describes** | doc to repo | the doc lives inside that repo's tree |
| **links-to** | doc to doc or repo | a `[[wiki-link]]` in the doc body |
| **mentions** | doc to doc or repo | the name shows up in prose (weakest, dimmed, with a toggle to hide it) |

Open the result and it behaves like a workbench, not a poster.

```
┌──────────────────────────────────────────────┬───────────────────────┐
│  search repos + docs…   [reset][focus][○ ...] │  Architecture  ·doc   │
│                                                │  links: api, storage  │
│       ┌─────┐         ┌─────────┐              │  linked from: api/RE… │
│       │ api │────────▶│ storage │   ← repos    │  ───────────────────  │
│       └──┬──┘         └────┬────┘              │  # Architecture       │
│        · api/README     · storage/README       │  api is the entry;    │
│       · · · ·  knowledge band  · · · ·         │  storage is the core. │
│       ▢ architecture     ▢ adr-001-storage     │  > Rule: api never    │
│   pan · zoom · click a doc to read it rendered │  >   imports a peer.  │
└──────────────────────────────────────────────┴───────────────────────┘
```

- Pan and zoom the graph. The wheel zooms about the cursor, drag pans, and one button resets the view.
- Search repos and doc titles at the same time. Whatever doesn't match fades back.
- Click a doc and read its rendered markdown right there, with headings and lists and tables and code, and `[[links]]` you can click to jump to the node they name.
- Double-click any node to narrow the view to its neighborhood. Click once to clear it.
- A breadcrumb trail remembers your path, so following a link is always reversible.

A rendered sample ships with the repo at [`examples/atlas-demo.html`](examples/atlas-demo.html). Open it directly, or regenerate it with `python examples/atlas_demo.py`.

> The markdown is rendered server-side and escaping-safe, so untrusted doc content can't inject anything. The whole file is self-contained, with no external fonts, scripts, or stylesheets.

---

## What you get

| Output | Command | Description |
|--------|---------|-------------|
| **Code + knowledge dashboard** | `index atlas --format html` | The two-layer map: repos and docs, pan and zoom, search, rendered markdown, `[[links]]` |
| **Atlas pack (JSON)** | `index atlas --json` | The two-layer graph as data, a strict superset of the context pack |
| **Interactive dependency dashboard** | `index viz --format html` | Self-contained. Click nodes, follow evidence tooltips, see cycles highlighted |
| **Layered SVG** | `index viz --format svg` | Static vector graph for docs or CI artifacts |
| **Mermaid diagram** | `index viz --format mermaid` | Paste into GitHub markdown or any Mermaid renderer |
| **JSON context manifest** | `index map` | Machine-readable inventory: remotes, branches, dirty counts, classification |
| **Dependency graph (text/JSON)** | `index graph [--cycles]` | Repo to repo edges with evidence, and a report of dependency cycles |
| **Context pack (prose + relations)** | `index context` | Synthesis pack: roles, relations, narrative summary |

---

## CLI reference

```
index atlas   [--root ROOT] [--format html] [--json] [--out FILE] [--no-external]
index map     [--root ROOT] [--output FILE] [--json] [--config CFG]
index graph   [--root ROOT] [--json] [--cycles]
index context [--root ROOT] [--focus REPO]
index viz     [--root ROOT] [--format {html,svg,mermaid,all}]
              [--focus REPO] [--no-external] [--out FILE] [--out-dir DIR]
```

`--focus REPO` narrows a `viz` or `context` render to one repo's dependency neighborhood.
`--no-external` hides stdlib and third-party nodes, keeping the graph to your own repos.
In the `atlas` dashboard, focus is interactive. Just double-click a node.

---

## How an edge earns its place

An edge you can't trace is a rumor. `index` resolves each one from two independent signals, and grades how well they agree.

```mermaid
flowchart TD
    n_api["api"]
    n_core["core"]
    n_cli["cli"]
    n_pathlib(("pathlib"))
    n_requests(("requests"))
    n_core --> n_pathlib
    n_api --> n_core
    n_cli --> n_api
    n_cli --> n_requests
```

When a manifest dependency and an observed import point the same way, you get a high-confidence edge. When only one of them does, it still gets recorded, along with the exact file and line that witnesses it. Nothing enters the graph on faith.

---

## Configuration

Drop an optional `.index.toml` at your workspace root:

```toml
# .index.toml, at your workspace root
[[rule]]                  # classify repos by workspace-relative path; first match wins
pattern = "oss/**"
class   = "public"

[[rule]]
pattern = "work/**"
class   = "internal"

[scan]
jobs  = 16                    # parallel workers
prune = ["vendor", "target"]  # extra dirs to skip (added to the built-in safety set)

[privacy]
omit_origin_classes = ["internal"]   # drop remote URLs for repos in these classes

[output]
portable = true               # root-relative paths + hashed root (default on)
```

See [`example.index.toml`](example.index.toml) for the full schema, and [`USAGE.md`](USAGE.md) for the complete flag reference, the importable Python API, and worked examples.

---

## What you can count on

- Evidence on every edge. No dependency edge exists without a file and line that witnesses it, and a confidence grade. The atlas edges (`describes`, `links-to`, `mentions`) come from location and `[[links]]`, not from a hunch.
- The same input gives the same output. Run it twice on a workspace and the JSON and the render come back identical, byte for byte. No timestamps, no randomness.
- Nothing to install but Python. Pure 3.11+ standard library, including the markdown renderer and the dashboard's pan and zoom. A test keeps it that way.
- Self-contained, and safe with untrusted docs. One HTML file, no external URLs. Markdown is escaped as it renders, and a hostile-content test proves it can't break out.
- Private by default. Repo paths are kept root-relative, the local root is reduced to a short hash, and anything that looks like a credential in a remote URL is redacted.

---

## Install

```bash
pip install index-graph
```

Or from a checkout:

```bash
pip install -e .
```

Python 3.11+. That is the entire dependency list.

---

`index` exists because a codebase should be something you can see into, not something you rebuild from memory every time a new person walks in. Point it at your repos, open the file it writes, and the shape is just there. The same shape on every run, with the evidence for every edge a click away.

Zain Dana Harper. [Portfolio](https://harperz9.github.io), [GitHub](https://github.com/HarperZ9).
Built with Claude Code. Reviewed, tested, and owned by me.
