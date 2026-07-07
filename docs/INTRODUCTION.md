# An introduction to index

`index` maps codebases. Point it at one repository and it derives a
self-contained wiki: module pages, symbol pages, an architecture diagram, and
your own docs, all from the code's real structure. Point it at a folder of
repositories and it draws the whole workspace: which repos depend on which,
down to the file and line that shows each edge, with your markdown joined to
the code it explains. Every command writes one offline HTML file or one JSON
document. No server, no account, no model, no network, no dependencies beyond
Python 3.11+.

It reads nine ecosystems from their manifests and their real imports: Python,
JavaScript and TypeScript, Rust, Go, Java, C#, Ruby, PHP, and C and C++.
Python additionally gets symbol-level depth: go-to-definition,
find-references, and find-implementations, from the CLI or inside your editor
via a built-in LSP server.

## Why it exists

A codebase's shape usually lives in someone's head, and that person is busy or
gone. Tools that regenerate the shape tend to guess: model-based wiki
generators write fluent prose about structure that is not there, and pretty
graph views go stale without saying so. `index` takes a different position:
it only draws what it can point to, and everything it draws can be re-checked
by anyone with one command. That is the whole philosophy, and this is the last
paragraph about it. The rest of this document is what the tool does.

## Core concepts

**The workspace and the repo.** Most commands take `--root`. When the root is
a folder of git repositories, you are at workspace altitude: `map`, `graph`,
`atlas`, `workbench`, `viz`, `context`. When the root is a single repository,
you are at repo altitude: `wiki`, `internals`, `internals-symbols`, `symbols`,
`lsp`.

**Evidence-backed edges.** A dependency edge enters the graph only with a
witness: a manifest line, an observed import, or both, each with its
`file:line`. When manifest and import agree the edge is high confidence; a
single signal is still recorded, and graded. Nothing enters on faith.

**The two-layer map.** Code is half of a system; the prose that explains it is
the other half. `index atlas` makes every markdown file a node joined to the
repo it lives in, turns `[[wiki-links]]` into edges, and renders the doc text
inside the map, so the explanation sits next to the thing it explains.

**Sealed artifacts and verdicts.** The wiki, the architecture check, and the
drift report are not just outputs, they are claims, so each one seals enough
information to be re-checked. A verification answers with one of three words:
MATCH, DRIFT, or UNVERIFIABLE. There is no fourth word and no TRUSTED. When
the tool cannot evaluate something, it says so instead of guessing.

**The context budget, made visible.** `index context-envelope` builds a
token-budgeted context packet for agent workflows: retained repos carry hashed
source references, and anything dropped carries a typed failure code such as
`budget_exceeded`. `index lens` renders the same computation as a page with a
live budget slider, replaying the exact retention rule the CLI runs, so you
can see what any budget keeps and drops before you spend it.

## The first ten minutes

Install:

```bash
pip install index-graph
index --version        # index 2.8.0
```

### Minute one: a repo you have never read

Pick any repository, yours or someone else's:

```bash
index wiki https://github.com/org/repo --out wiki.html
```

`index` shallow-clones it to a temp directory, derives the wiki from the
module and symbol graph, deletes the clone, and writes one HTML file. Open it.
The overview page shows the detected ecosystems, the entry points the graph
implies, and the commit the wiki is pinned to. Each module page lists imports
and dependents with the `file:line` that proves each one. For Python repos,
each function, class, and method gets a page with its callers and callees.
Your existing markdown is included verbatim, labeled as human-authored.

For a repo already on disk, use `--root`:

```bash
index wiki --root /path/to/repo --out wiki.html
```

### Minute four: re-check it

```bash
index wiki --verify wiki.html --root /path/to/repo
```

Expect a line like `verdict=MATCH pages=31 edges=127` and exit code 0. Now
edit a source file and run the verify again: the verdict becomes DRIFT, exit
code 1, and the report names what moved. This is the loop the whole tool is
built around: generate, then let anyone re-check.

### Minute six: the whole workspace

Move up one altitude. From a folder that contains several repositories:

```bash
index workbench --root /path/to/workspace --out workbench.html
```

One page with everything: the repo and doc map (pan, zoom, search,
double-click to focus), rendered markdown for the docs, the context lens with
its budget slider, and a health panel with the workspace fingerprint,
dependency cycles, and doc coverage. On very large workspaces the page keeps
itself renderable with explicit budgets: dropped items are counted and shown
as "N of M", never silently truncated, and every cap has a CLI override.

If you want the surfaces separately: `index atlas` for the two-layer map,
`index viz` for the dependency dashboard (also `--format svg` and
`--format mermaid`), `index graph --cycles` for a plain-text cycle report.

### Minute nine: make the architecture a rule

Write down the layering you meant, in `.index.toml` at the root:

```toml
[architecture]
layers = ["core", "service", "web"]
forbid = [{ from = "core/**", to = "web/**" }]
max_cycles = 0
```

Then:

```bash
index check --json
```

Every breach comes back with its `file:line`, and the command exits non-zero
on failure, so it drops straight into CI. From here, `index snapshot` and
`index drift` track the shape over time, and `index check --freshness` plus
`index freshness` tell you whether a stored verdict still describes the
current tree.

## Where to go next

- [`USAGE.md`](../USAGE.md): the complete flag reference, the importable
  Python API, and worked examples for every command.
- [`docs/PROTOCOL.md`](PROTOCOL.md): the JSON schemas of the certificates,
  receipts, and packs, for consuming them from other tools.
- [`docs/ENTERPRISE-READINESS.md`](ENTERPRISE-READINESS.md): integration notes
  for unattended agent workflows, including the MCP server (`index mcp`).
- [`examples/`](../examples): rendered sample artifacts
  (`wiki-demo.html`, `atlas-demo.html`) and the deterministic scripts that
  regenerate them.
- For editors: `index lsp --root REPO` speaks stdio LSP to VSCode, Neovim,
  and JetBrains, serving go-to-definition and find-references from the same
  symbol graph as `index symbols`.
- Peer projects in [Project Telos](https://harperz9.github.io):
  [gather](https://github.com/HarperZ9/gather),
  [crucible](https://github.com/HarperZ9/crucible),
  [forum](https://github.com/HarperZ9/forum),
  [telos](https://github.com/HarperZ9/telos).
