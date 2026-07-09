<p align="center"><img src=".github/assets/banner.svg" alt="index: Maps a multi-repo workspace in seconds: nine ecosystems, dependency and symbol graphs, fully offline, zero dependencies." width="100%"></p>

**Maps a multi-repo workspace in seconds: nine ecosystems, dependency and symbol graphs, fully offline, zero dependencies.**

[![PyPI](https://img.shields.io/pypi/v/index-graph?style=flat-square&labelColor=14041b&color=26dfe8)](https://pypi.org/project/index-graph/)
[![license: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-8f8095?style=flat-square&labelColor=14041b)](LICENSE)
[![CI](https://github.com/HarperZ9/index/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/index/actions/workflows/ci.yml)
[![downloads](https://img.shields.io/pypi/dm/index-graph?label=downloads&style=flat-square&labelColor=14041b)](https://pypi.org/project/index-graph/)
![python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square&labelColor=14041b)
![deps: none](https://img.shields.io/badge/deps-none-success?style=flat-square&labelColor=14041b)

[Project Telos](https://harperz9.github.io) | [gather](https://github.com/HarperZ9/gather) | [crucible](https://github.com/HarperZ9/crucible) | [index](https://github.com/HarperZ9/index) | [forum](https://github.com/HarperZ9/forum) | [telos](https://github.com/HarperZ9/telos) | [learn](https://github.com/HarperZ9/learn) | [emet](https://github.com/HarperZ9/emet) | [buildlang](https://github.com/HarperZ9/buildlang)

Point `index` at one unfamiliar repo and get a self-contained wiki with module, symbol, and architecture pages. Point it at a whole workspace and get the dependency atlas with your docs joined to the code they explain, or the workbench, which folds map, docs, context lens, and health into one page. Every command writes one offline HTML file: no server, no account, no model, no network. `pip install index-graph` installs it, `index` runs it, `import index_graph` imports it.

## Try it in 5 minutes

```bash
pip install index-graph

# one unfamiliar repo -> one self-contained wiki, then re-check it
index wiki --root /path/to/one/repo --out wiki.html
index wiki --verify wiki.html --root /path/to/one/repo
# verdict=MATCH pages=31 edges=127        (exit 0; DRIFT=1, UNVERIFIABLE=2)

# a whole workspace -> every surface on one page
index workbench --root /path/to/workspace --out workbench.html

# or individual surfaces:
index atlas --root /path/to/workspace --format html --out atlas.html
index viz   --root /path/to/workspace --format html --out graph.html
```

Each command writes one self-contained HTML file. Open it in any browser, offline. Nothing to host, nothing phones home.

Want to see the output before installing? Rendered samples ship with the repo: [`examples/wiki-demo.html`](examples/wiki-demo.html) for the single-repo wiki and [`examples/atlas-demo.html`](examples/atlas-demo.html) for the workspace atlas. They regenerate deterministically with `python examples/wiki_demo.py` and `python examples/atlas_demo.py`.

New here? [`docs/INTRODUCTION.md`](docs/INTRODUCTION.md) is the ten-minute walkthrough.

---

## What it does

Every codebase has a shape. Past a handful of repos, that shape lives only in someone's head, and they are usually busy or already gone. `index` draws it for you: how your repositories depend on each other, what lives inside each one down to the symbol level, and the docs that explain why, as maps you can open, search, and re-derive. It reads nine ecosystems (Python, JavaScript and TypeScript, Rust, Go, Java, C#, Ruby, PHP, C and C++) from their manifests and their real imports, and it records each dependency edge with the file and line that shows it. Pure Python 3.11+ standard library, zero runtime dependencies.

## The surfaces, coolest first

**`index wiki`, the single-repo wiki.** Model-based wiki generators write confident prose about structure that is not there; repo packers dump source without comprehending it. `index wiki` takes the third path: it derives the wiki for one repo from the module and symbol graph it extracts itself, and generates no prose at all. You get an overview page, one page per module with imports, dependents, and cycle membership, one page per Python function, class, and method with its callers and callees, and an architecture diagram rendered from the real dependency graph. Point it at a git URL (`index wiki https://github.com/org/repo`) and it shallow-clones, derives, and cleans up, so you can read a repo you have not checked out. The artifact is commit-pinned and sealed, and `index wiki --verify` re-checks it against the current tree: MATCH, DRIFT, or UNVERIFIABLE, exit codes 0, 1, 2.

**`index workbench`, every surface on one page.** One pass over a workspace, one HTML file: the repo and doc map you pan and zoom, rendered markdown for the docs, the context lens with its live budget slider, and a health panel with the workspace fingerprint, dependency cycles, and doc-coverage audit. Large workspaces stay renderable: page-weight budgets cap how many doc bodies and weak edges embed, every cap prints what it dropped as "N of M", and every cap is overridable at the CLI (`--max-doc-bodies`).

**`index atlas`, the two-layer map.** Most dependency tools stop at the code. The atlas joins your markdown to it: every doc becomes a node next to the repo it lives in, `[[wiki-links]]` become edges you can click, and you read the rendered doc without leaving the map. Search covers repos and docs at once, double-click narrows to a node's neighborhood, and a breadcrumb trail makes every jump reversible. Four edge kinds, each derived from something real: depends-on (import or manifest line), describes (the doc lives in that repo), links-to (a wiki-link in the body), mentions (name in prose, dimmed, hideable).

**`index lens`, the context lens.** Agent context assembly is usually invisible: a budget retains some files and silently drops the rest. The lens renders it. One page shows what a token budget retains and what it drops with typed failure codes, and a slider replays the exact greedy rule the CLI runs over the exact same numbers, live, without re-running Python. `index context-envelope` is the machine face of the same thing: a budgeted context packet where each retained repo carries hashed source references and every omission carries a failure code such as `budget_exceeded`, so a downstream agent can ask for more instead of inheriting confidence from a missing file.

**`index symbols` and `index lsp`, IDE navigation from the graph.** Go-to-definition, find-references, and find-implementations for any Python symbol, from the CLI (`index symbols Class::method`) with `file:line` on every hop, or inside VSCode, Neovim, and JetBrains via a stdio LSP server with hand-rolled JSON-RPC framing and zero new dependencies. An unresolved reference returns empty, never a guessed jump, and a workspace that changed on disk is detected rather than answered from a stale graph. `index internals` and `index internals-symbols` expose the underlying module and call graphs directly.

**`index check`, `snapshot`, `drift`, architecture as a testable rule.** Declare the layering you meant in `.index.toml`:

```toml
[architecture]
layers = ["core", "domain", "service", "web"]   # a lower layer may not import a higher one
forbid = [{ from = "core/**", to = "web/**" }]
require = [{ from = "web", to = "core" }]
max_cycles = 0
```

`index check` measures the real graph against it, reports every breach with the file and line that shows it, and exits non-zero, so it sits in CI as a gate. `index snapshot` then `index drift` diff the shape across time. `index check --freshness` stamps a certificate with a workspace fingerprint and `index freshness` later answers FRESH or STALE; `index invalidate` goes further and names exactly which artifacts a change invalidated, with typed reasons.

**`index serve`, the on-demand wiki server.** A local stdlib server: request any repo by its forge path (`http://127.0.0.1:8000/github.com/org/repo`) and get its wiki, derived that moment by the same code path as `index wiki`, then discarded. Nothing is crawled or pre-indexed, `robots.txt` disallows indexing, every page defers to the repo owner's authored docs, and it binds loopback by default.

**`index mcp`, the agent face.** A stdio MCP server exposing the map, context, envelope, selection, wiki, symbol, and verification surfaces as native tools, so an agent host gets the same evidence-backed answers the CLI gives.

---

## Command reference

```
index                                            # bare: writes INDEX.json, prints the path first
index map       [--root ROOT] [--json] [--dry-run] [--config CFG]
index graph     [--root ROOT] [--json] [--cycles]
index viz       [--root ROOT] [--format {html,svg,mermaid,all}] [--focus REPO] [--no-external]
index atlas     [--root ROOT] [--format html] [--json] [--out FILE] [--no-external]
index workbench [--root ROOT] [--budget N] [--max-doc-bodies N] [--out FILE] [--json]
index wiki      [SOURCE] [--root REPO] [--out PATH] [--format {html,json}]
index wiki      --verify PATH [--root REPO] [--json]
index serve     [--host HOST] [--port PORT]
index lens      [--root ROOT] [--budget N] [--focus REPO] [--out FILE] [--json]
index context   [--root ROOT] [--focus REPO] [--hops N] [--json] [--audit]
index context-envelope [--root ROOT] [--budget N] [--focus REPO] [--json]
index select    [--root ROOT] [--suffix S ...] [--max-files N] [--json]
index internals [--root REPO] [--json] [--cycles]
index internals-symbols [--root REPO] [--json] [--coverage]
index symbols   QUERY [--root REPO] [--def] [--refs] [--impls] [--json]
index lsp       [--root ROOT]
index check     [--root ROOT] [--internals] [--freshness] [--json] [--config CFG]
index snapshot  [--root ROOT] --out FILE
index drift     --from OLD --to NEW [--json]
index freshness --cert CERT [--root ROOT] [--json]
index invalidate [--root ROOT] (--out PIN | --pin PIN) [--json]
index verify    [--root ROOT] [--depends "A -> B" | --exists NAME] [--json]
index router    [--root ROOT] [--out FILE]
index bench     [--root ROOT] [--json]
index status | doctor | demo [--json]
index mcp
```

The full flag reference, the importable Python API, and worked examples live in [`USAGE.md`](USAGE.md). Artifact schemas are written down in [`docs/PROTOCOL.md`](docs/PROTOCOL.md) so other tools can consume them without knowing anything about `index`.

## Operator surface

For hosts and unattended workflows, `index status --json`, `index doctor --json`, and `index demo --json` expose the machine-readable action envelope, and `index mcp` serves the same map, context, envelope, selection, wiki, symbol, and verification surfaces as native MCP tools. The status payload advertises the shared CLI/MCP/plugin/IDE contracts, so an agent host can discover what this installation supports before calling it:

```bash
# from a source checkout
python -m index status --json
```

Within [Project Telos](https://harperz9.github.io), this operator surface is how `index` acts as the workspace map and context-envelope layer for gather, forum, crucible, and telos. Integration notes for unattended agent workflows are in [`docs/ENTERPRISE-READINESS.md`](docs/ENTERPRISE-READINESS.md).

## A worked example

Run the wiki on this repository itself:

```bash
git clone https://github.com/HarperZ9/index
index wiki --root index --out wiki.html
index wiki --verify wiki.html --root index
```

The verify step prints `verdict=MATCH pages=31 edges=127` and exits 0 (page and edge counts move with the code). Edit any source file and verify again: the verdict turns to DRIFT and the exit code to 1, naming the page and rule that failed. That is the property the whole tool is built on: the map is not something you trust, it is something anyone can re-run.

## Configuration

Everything works with zero configuration. An optional `.index.toml` at the workspace root adds path-based repo classification, scan tuning (`jobs`, `prune`), privacy rules for remote URLs, and the `[architecture]` block above. See [`example.index.toml`](example.index.toml) for the full schema.

## What you can count on

- Evidence on every edge: no dependency edge exists without a file and line behind it, and a confidence grade. Two independent signals (manifest and observed import) grade each one.
- Deterministic output: the same input gives the same bytes. No timestamps, no randomness.
- Zero runtime dependencies, including the markdown renderer, the SVG layout, and the LSP framing. A test keeps it that way; the suite currently collects 600 tests.
- Self-contained and safe with untrusted docs: one HTML file, no external URLs, markdown escaped as it renders, with hostile-content fixtures in the tests.
- Private by default: paths are root-relative, the local root reduces to a short hash, and credential-shaped fragments in remote URLs are redacted.

## Status

`index-graph` 2.9.0 on PyPI, command `index`, Python 3.11+, Development Status Beta. It is used as the workspace map layer of [Project Telos](https://harperz9.github.io), alongside [gather](https://github.com/HarperZ9/gather), [crucible](https://github.com/HarperZ9/crucible), [forum](https://github.com/HarperZ9/forum), and [telos](https://github.com/HarperZ9/telos).

One note on why the outputs look the way they do: every claim an `index` artifact makes, an edge, a page, a verdict, carries the evidence to re-derive it, and the verifiers are built to be able to fail. If you only remember one command, make it `index wiki --verify`.

## Install

```bash
pip install index-graph
```

Or from a checkout:

```bash
pip install -e ".[test]"
python -m pytest
```

Python 3.11+. That is the entire dependency list.

---

Zain Dana Harper. [Portfolio](https://harperz9.github.io), [GitHub](https://github.com/HarperZ9).
Built with Claude Code. Reviewed, tested, and owned by me.
