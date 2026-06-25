# Usage

`index` scans a workspace for Git repositories and shows you how they fit together. It began as a compact JSON inventory map, and it has grown into a small family of commands: the inventory map, a repo dependency graph built from real code evidence, a synthesis context pack, an interactive dependency dashboard, and `index atlas`, the two-layer map that brings your markdown docs in alongside the code. Version 2.0 adds a verified architecture layer: a module-level graph, a declarative `[architecture]` check, and drift detection, each backed by a re-checkable certificate. It ships a CLI (`index`) and a small importable Python API. There are no runtime dependencies, and it needs Python 3.11 or newer.

## Install

```bash
python -m pip install index-graph
```

Or from a checkout (editable):

```bash
python -m pip install -e .
```

## CLI

The console script is `index` (equivalently `python -m index_graph`). With no subcommand it runs `map`, which preserves the original flat invocation.

```text
index [--root ROOT] [--output OUTPUT] [--json]
      [--config CONFIG] [--jobs JOBS] [--version]
```

| Flag        | Default                          | Meaning                                              |
| ----------- | -------------------------------- | ---------------------------------------------------- |
| `--root`    | current directory                | Workspace root to scan.                              |
| `--output`  | `<root>/INDEX.json`              | Output path (ignored when `--json` is given).        |
| `--json`    | off                              | Print the JSON map to stdout instead of writing it.  |
| `--config`  | `<root>/.index.toml` if present  | Path to a `.index.toml`. A missing explicit path is fatal. |
| `--jobs`    | config or a CPU heuristic        | Override the parallel git worker count (must be at least 1). |
| `--version` | n/a                              | Print the version (for example `index 1.0.0`) and exit. |

With no config, classification falls back to a remote-host heuristic: `local` (no remote), `public` (the origin host is in the known public set), or `private`. Supply a `.index.toml` (see `example.index.toml`) for ordered path-glob rules.

### Example 1, print a map to stdout

```bash
index --root ./my-workspace --json
```

Example output (yours will differ in paths, hashes, and timestamps):

```json
{
  "schema_version": 1,
  "tool_version": "1.0.0",
  "generated_at": "2026-06-18T10:16:44-07:00",
  "root_sha256_prefix": "617a55395ac0d599",
  "absolute_paths_included": false,
  "repo_count": 2,
  "dirty_count": 0,
  "class_counts": {
    "public": 1,
    "local": 1
  },
  "top_level": [
    { "name": "proj-a", "kind": "directory", "class": "entry", "bytes": null,
      "modified": "2026-06-18T10:16:37-07:00" },
    { "name": "proj-b", "kind": "directory", "class": "entry", "bytes": null,
      "modified": "2026-06-18T10:16:37-07:00" }
  ],
  "repositories": [
    { "path": "proj-a", "class": "public", "branch": "main", "head": "eb4e19b",
      "origin": "https://github.com/example/proj-a.git",
      "dirty_count": 0, "untracked_count": 1, "markers": ["README.md"] },
    { "path": "proj-b", "class": "local", "branch": "main", "head": "e4f1b0c",
      "origin": "", "dirty_count": 0, "untracked_count": 0,
      "markers": ["pyproject.toml"] }
  ]
}
```

### Example 2, write a map file (default mode)

```bash
index --root ./my-workspace
```

Example output:

```text
wrote /path/to/my-workspace/INDEX.json
repos=2 dirty=0
```

The JSON file content matches the structure shown in Example 1.

### Example 3, custom output path and worker count

```bash
index --root ./my-workspace --output ./inventory.json --jobs 8
```

Example output:

```text
wrote /path/to/inventory.json
repos=2 dirty=0
```

### Example 4, use an explicit config

```bash
index --root ./my-workspace --config ./example.index.toml --json
```

Rules in the config are matched against each repo's workspace-relative path (first match wins) before the remote-host fallback. A `--config` path that does not exist is a fatal error (non-zero exit).

## Configuration (`.index.toml`)

Place a `.index.toml` at the workspace root (auto-discovered) or pass `--config PATH`. Every section is optional, and with no file the neutral remote-host heuristic applies.

```toml
# Ordered classification rules, first match wins. `pattern` is matched against each
# repo's workspace-relative POSIX path (and against top-level entry names).
[[rule]]
pattern = "oss/**"     # *  matches within one path segment (stops at "/")
class   = "public"     # ** matches across segments; "oss/**" also matches bare "oss"

[[rule]]
pattern = "work/**"
class   = "internal"

[scan]
jobs    = 16            # parallel git workers (default: a CPU heuristic)
prune   = ["vendor"]   # ADDED to the built-in safety set (.git, node_modules, .venv, ...)
markers = ["go.mod"]   # REPLACES the default marker-file list when present

[privacy]
omit_origin_classes = ["internal"]   # blank the `origin` for repos of these classes

[output]
portable    = true                   # false = absolute paths + a `root` field (private local maps)
annotations = { team = "infra" }     # arbitrary key/values emitted verbatim under "annotations"
```

When no rule matches a repo, classification falls back to the remote host. No remote becomes `local`, a public-hosting domain (`github.com`, `gitlab.com`, `bitbucket.org`, `codeberg.org`, `git.sr.ht`) becomes `public`, and anything else becomes `private`. Credential-shaped material in remote URLs is redacted in **every** mode. Setting `portable = false` additionally emits absolute paths and a `root` field, and is meant only for maps that never leave the machine.

## Python API

The package exposes a stable surface via `__all__`:

```python
from index_graph import (
    build_map, write_map, discover_repos,
    Map, RepoRow, SCHEMA_VERSION,
    Config, Rule, load_config, default_config,
    classify, __version__,
)
```

Key entry points:

- `build_map(root: Path, config: Config, tool_version: str) -> Map`. Scan and return the in-memory map.
- `write_map(root, config, tool_version, output: Path) -> Map`. The same, but also writes pretty JSON to `output`.
- `load_config(path: Path | None, root: Path) -> Config` and `default_config() -> Config`.
- `classify(path: str, is_repo: bool, origin: str, config: Config) -> str`.
- `Map.to_json()` and `RepoRow.to_json()`. Plain-dict serialization.

### Example, build a map in code

```python
from pathlib import Path
from index_graph import build_map, default_config, __version__

config = default_config()
m = build_map(Path("./my-workspace"), config, __version__)

print(m.repo_count, m.dirty_count)   # e.g. 2 0
print(m.class_counts)                # e.g. {'public': 1, 'local': 1}
for row in m.repositories:
    print(row.path, row.class_, row.branch, row.head)
```

Example output:

```text
2 0
{'public': 1, 'local': 1}
proj-a public main eb4e19b
proj-b local main e4f1b0c
```

### Example, classify a single path

```python
from index_graph import classify, default_config

cfg = default_config()
classify("proj-a", True, "https://github.com/example/proj-a.git", cfg)  # -> "public"
classify("proj-b", True, "", cfg)                                       # -> "local"
```

## Dependency graph and context pack

`index` can infer a repo to repo dependency graph from real code, and emit a synthesis context pack with roles, relations, and extracted prose.

### `graph` subcommand

```text
index graph --root ROOT [--json] [--cycles]
```

| Flag       | Default           | Meaning                                                     |
| ---------- | ----------------- | ----------------------------------------------------------- |
| `--root`   | current directory | Workspace root to scan.                                     |
| `--json`   | off               | Emit a JSON array of relation objects instead of text.      |
| `--cycles` | off               | Report dependency cycles instead of the full graph.         |

Edges are derived from Python (`pyproject.toml`, `setup.cfg`, source imports) and JavaScript or TypeScript (`package.json`, source imports). Each edge carries the file (and line) that witnesses it, and a confidence grade:

- `high`: both a declared dependency and an observed import agree.
- `moderate`: a single signal, manifest-only or import-only.
- `low`: the name is ambiguous (two different repos expose the same normalized name), or the target name is too short to resolve reliably.

With `--cycles`, `index graph` lists any dependency cycles it finds and says so plainly when the graph is a clean DAG.

#### Example, `graph --json` output shape

```json
[
  {
    "from": "py-app",
    "to": "py-lib",
    "external": false,
    "confidence": "high",
    "signals": [
      { "kind": "manifest", "file": "py-app/pyproject.toml", "line": null, "raw": "py-lib" },
      { "kind": "import",   "file": "py-app/py_app/cli.py",  "line": 3,    "raw": "import py_lib" }
    ]
  }
]
```

### `context` subcommand

```text
index context --root ROOT [--json] [--focus REPO] [--audit]
```

| Flag           | Default           | Meaning                                                         |
| -------------- | ----------------- | --------------------------------------------------------------- |
| `--root`       | current directory | Workspace root to scan.                                         |
| `--json`       | off               | Emit the context pack as JSON instead of Markdown.              |
| `--focus REPO` | none              | Emit only the named repo's dependency neighborhood (bidirectional closure). |
| `--hops N`     | none (full)       | Bound `--focus` to an N-hop neighborhood; the pack then carries a `preserved` manifest naming what it kept and the boundary edges and nodes it dropped, so a compact pack declares its losses. |
| `--audit`      | off               | Print only the salience-faithfulness audit (hubs and mismatches), not the pack. |

Exit codes:

- `0`: the context pack was written or printed successfully.
- `2`: `--focus <repo>` names a repo not found in the workspace. A near-match hint is printed to stderr.

The map subcommand (`index map`, or the flat `index --root ...`) is unaffected.

### `viz` subcommand

```text
index viz --root ROOT [--format FORMAT] [--focus REPO] [--no-external] [--out PATH | --out-dir DIR]
```

| Flag           | Default           | Meaning                                                                  |
| -------------- | ----------------- | ------------------------------------------------------------------------ |
| `--root`       | current directory | Workspace root to scan.                                                  |
| `--format`     | html              | Output format: `html`, `svg`, `mermaid`, or `all` (every format plus a manifest). |
| `--focus REPO` | none              | Render only the named repo's dependency neighborhood (bidirectional closure). |
| `--no-external`| off               | Omit external (third-party) dependencies from the graph.                 |
| `--out PATH`   | `<root>/graph.html` (or format-dependent) | Write a single format to a specific file path. |
| `--out-dir DIR`| `<root>/`         | Write all outputs to a directory.                                        |

#### Format details

- **html** (default): a self-contained interactive dashboard. Click a node to see its dependencies and evidence, filter by role and confidence, read an edge tooltip back to the witnessing file, and see cycles highlighted. It opens from `file://` with no external URLs and no runtime dependencies, and a double render of the same input is byte-identical. (Pan and zoom live in `index atlas`, below.)
- **svg**: a standalone SVG network graph, good for embedding or printing. Self-contained and deterministic.
- **mermaid**: Mermaid flowchart markup (`.mmd`). It renders in GitHub markdown and online Mermaid editors. Deterministic, though it needs a Mermaid renderer to produce the picture.
- **all**: writes `graph.html`, `graph.svg`, `graph.mmd`, `context.json`, and `context-manifest.json`. The manifest holds artifact paths and per-file SHA-256 hashes, for auditing and for handing off to a static-site builder or asset verifier.

#### Example, render the full graph as HTML

```bash
index viz --root ./my-workspace
```

This writes `/my-workspace/graph.html`. Open it in any browser from `file://`.

#### Example, render one repo's neighborhood as a Mermaid diagram

```bash
index viz --root ./my-workspace --focus my-app --format mermaid --out ./my-app-deps.mmd
```

#### Example, batch render all formats with a manifest

```bash
index viz --root ./my-workspace --format all --out-dir ./viz-output
```

This writes `viz-output/graph.{html,svg,mmd}`, `context.json`, and `context-manifest.json`.

### `atlas` subcommand

`index atlas` is the headline. It builds the same dependency graph and then layers your markdown documents on top of it, so the code and the prose that explains it sit on one map.

```text
index atlas --root ROOT [--format html] [--json] [--out PATH] [--no-external]
```

| Flag            | Default           | Meaning                                                                 |
| --------------- | ----------------- | ----------------------------------------------------------------------- |
| `--root`        | current directory | Workspace root to scan.                                                 |
| `--format html` | none              | Render the interactive two-layer dashboard as one self-contained HTML file. |
| `--json`        | off               | Print the two-layer pack as JSON (a strict superset of the context pack). |
| `--out PATH`    | stdout            | Write the HTML to a file instead of printing it.                        |
| `--no-external` | off               | Omit external (third-party) dependency nodes.                           |

With neither `--format` nor `--json`, `atlas` prints a one-line summary with the repo, doc, and edge counts.

The pack adds three keys on top of the context pack:

- `docs`: one entry per markdown file, as `{ "id": <workspace-relative path>, "title": <first heading or filename>, "dir": <directory> }`.
- `knowledge_edges`: the doc edges, each as `{ "type": "describes" | "links-to" | "mentions", "from": <doc id>, "to": <repo name or doc id>, "to_kind": "repo" | "doc" }`.
- `knowledge_warnings`: any `[[wiki-link]]` that did not resolve to a repo or doc.

The three doc edge types come from evidence, not inference. `describes` means the doc lives inside that repo's tree. `links-to` comes from a `[[wiki-link]]` in the body. `mentions` comes from a repo or doc name appearing in prose, and it is the weakest of the three, so it is deduped against the stronger two and dimmed in the dashboard.

#### Example, the atlas pack shape

```json
{
  "repos": [ "..." ],
  "relations": [ "..." ],
  "docs": [
    { "id": "api/README.md", "title": "API", "dir": "api" },
    { "id": "docs/architecture.md", "title": "Architecture", "dir": "docs" }
  ],
  "knowledge_edges": [
    { "type": "describes", "from": "api/README.md", "to": "api", "to_kind": "repo" },
    { "type": "links-to",  "from": "api/README.md", "to": "docs/architecture.md", "to_kind": "doc" }
  ],
  "knowledge_warnings": []
}
```

#### Example, render the two-layer dashboard

```bash
index atlas --root ./my-workspace --format html --out atlas.html
```

Open `atlas.html` in any browser, offline. Pan and zoom the graph, search repos and doc titles together, click a doc to read its rendered markdown with clickable `[[links]]`, and double-click a node to focus its neighborhood. The whole file is self-contained, and the markdown is rendered server-side and escaped, so untrusted doc content cannot inject anything.

## Verified architecture intelligence

Beyond drawing the shape, `index` can look inside a repo, measure the real structure against a rule you declare, watch it change over time, and hand back a verdict you can re-run. These commands are additive; the five above are unchanged. Everything here runs offline, with no API, account, or model.

### `internals` subcommand

```text
index internals --root REPO [--json] [--cycles]
```

| Flag       | Default           | Meaning                                                       |
| ---------- | ----------------- | ------------------------------------------------------------- |
| `--root`   | current directory | The single repo to look inside.                               |
| `--json`   | off               | Emit the module graph as JSON (modules, edges, cycles, fan).  |
| `--cycles` | off               | Report only the internal cycles.                              |

The module graph is exact for Python (read from the syntax tree) and best-effort and file-level for JavaScript, TypeScript, Rust, and Go. Java stays repo-level. Each internal edge names the file and line that witnesses it. The bounds are stated in `docs/PROTOCOL.md`.

#### Example, internals summary

```bash
index internals --root ./my-repo
```

```text
modules=50 edges=94 cycles=0 coverage=complete
```

The summary ends with coverage: `complete` when every file parsed and every import resolved statically, otherwise a count of the files the scan could not parse and the dynamic imports it could not follow. `--json` carries the detail under a `coverage` object, and `index check --internals` folds the same coverage into the certificate so a verdict is honest about its soundness scope.

### The `[architecture]` criterion

A check needs a rule to measure against. Declare one in `.index.toml`:

```toml
[architecture]
# ordered layers, lowest first; a lower layer may not import a higher one
layers = ["core", "domain", "service", "web"]
# edges that must never exist, by repo or module glob
forbid = [{ from = "core/**", to = "web/**" }]
# edges that must exist (an intended dependency); a missing one is an "absence"
require = [{ from = "web", to = "core" }]
# the most dependency cycles tolerated (omit to leave cycles unchecked)
max_cycles = 0
# optional ownership assertions
[architecture.owns]
"payments/**" = "team-payments"
```

The block is optional. With none declared, `check` returns UNVERIFIABLE rather than a hollow pass.

### `check` subcommand

```text
index check --root ROOT [--internals] [--json] [--config CFG]
```

| Flag          | Default              | Meaning                                                   |
| ------------- | -------------------- | --------------------------------------------------------- |
| `--root`      | current directory    | Workspace root to scan.                                   |
| `--internals` | off                  | Include intra-repo module checks, not only repo-level.    |
| `--json`      | off                  | Emit the certificate as JSON.                             |
| `--config`    | `<root>/.index.toml` | Path to the config holding the `[architecture]` block.    |

`check` exits non-zero when the verdict is not MATCH, so it works directly as a CI gate. Each finding names the rule it broke, the offending edge, and the file and line. A `require` rule whose intended edge is missing yields an `absence` finding, so `check` catches both edges that must not exist and edges that must (the Reflexion-model triad: convergence, divergence, absence).

#### Example, a check certificate

```bash
index check --root . --json
```

```json
{
  "schema": "index.certificate/1",
  "tool_version": "2.0.0",
  "kind": "check",
  "content_sha256": "…",
  "criterion_sha256": "…",
  "verdict": "DRIFT",
  "findings": [
    { "rule": "layer", "detail": "core must not depend upward on web",
      "edge": "core -> web", "evidence": "core/db.py:12" }
  ],
  "recheck": "index check --root . --json"
}
```

### `snapshot` and `drift` subcommands

```text
index snapshot --root ROOT --out FILE
index drift --from OLD --to NEW [--json]
```

`snapshot` writes a canonical, byte-stable projection of the graph. `drift` diffs two snapshots into added and removed repos and edges, introduced and cleared cycles, and role changes, with a MATCH or DRIFT verdict. Like `check`, `drift` exits non-zero on DRIFT.

#### Example, watch for drift in CI

```bash
index snapshot --root . --out baseline.json    # record once, commit it
# later, in CI:
index snapshot --root . --out now.json
index drift --from baseline.json --to now.json
```

### The certificate and the protocol

Both `check` and `drift` return a certificate whose verdict is one of three words, MATCH, DRIFT, or UNVERIFIABLE, never a fourth. You confirm it by re-running its `recheck` command and recomputing its hashes, not by trusting it. The snapshot and certificate shapes, the hashing rule, and the resolution bounds are specified in [`docs/PROTOCOL.md`](docs/PROTOCOL.md), so any consumer, whether a CI job, a reviewer, or another tool, can read them without depending on `index`.

## Workspace map (`router`)

`index router` renders a deterministic, evidence-carrying map of the workspace, shaped for a model's `CLAUDE.md` or `AGENTS.md`: where each repo lives with its role and dependencies, the entry points, the depended-on core, and which docs describe what. It is derived from the dependency graph and the docs atlas and re-runs identically, so it replaces the `index.md` plus read-first plus brief that teams maintain by hand.

```text
index router --root ROOT [--out FILE]
```

With `--out` it writes the map to a file; otherwise it prints to stdout. Every line is a graph fact (roles, edges, doc-describes), nothing invented.

## Grounding a claim (`verify`)

`index verify` is a deterministic oracle for a single structural claim, so a model can confirm what it is about to act on instead of trusting its memory. `--depends "A -> B"` asks whether A depends on B; `--exists NAME` asks whether a repo exists. The answer is one of three: MATCH (true, with the file:line that witnesses it), REFUTED (false), or UNVERIFIABLE (the claim names a repo not in the workspace).

```text
index verify --root ROOT [--depends "A -> B" | --exists NAME] [--json]
```

It exits 0 on MATCH, 1 on REFUTED, 2 on UNVERIFIABLE, and `--json` emits a re-checkable record (`index.verification/1`) carrying the content hash and the exact command to re-run.

## Agent protocol face (`mcp`)

`index mcp` serves a zero-dependency, MCP-shaped protocol over stdin and stdout: newline-delimited JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`), no SDK and no model. An agent host or orchestrator connects and calls index's deterministic tools by name.

```text
index mcp
```

The tools are `index_graph`, `index_focus` (a repo's neighborhood plus the preservation manifest), `index_verify` (ground a depends or exists claim), `index_router` (the workspace map), and `index_internals` (a repo's module graph). Each reuses the same function its matching subcommand does, so the protocol face never disagrees with the CLI.

## Notes

- This CLI is agent assisted. Review the output before sharing it in public.
- Maps are portable by default. Repo paths are root-relative, the absolute root is replaced by a short hash prefix, and credential-shaped material in remote URLs is redacted.
- The output schema is versioned (`schema_version: 1`).
