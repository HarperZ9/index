# Usage

`index` scans a workspace root for Git repositories and emits a compact
JSON inventory map. It ships a CLI (`index`) and a small importable Python
API. Runtime dependencies: none. Python: 3.11+.

## Install

```bash
python -m pip install index-graph
```

Or from a checkout (editable):

```bash
python -m pip install -e .
```

## CLI

The console script is `index` (equivalently `python -m index_graph`).

```text
index [--root ROOT] [--output OUTPUT] [--json]
      [--config CONFIG] [--jobs JOBS] [--version]
```

| Flag        | Default                          | Meaning                                              |
| ----------- | -------------------------------- | ---------------------------------------------------- |
| `--root`    | current directory                | Workspace root to scan.                              |
| `--output`  | `<root>/INDEX.json` | Output path (ignored when `--json` is given).        |
| `--json`    | off                              | Print the JSON map to stdout instead of writing it.  |
| `--config`  | `<root>/.index.toml` if present | Path to a `.index.toml`. Missing explicit path is fatal. |
| `--jobs`    | config / CPU heuristic           | Override the parallel git worker count (must be ≥ 1).|
| `--version` | —                                | Print `index 1.0.0` and exit.           |

Classification with no config falls back to a remote-host heuristic: `local` (no
remote), `public` (origin host in the known public set), or `private`. Supply a
`.index.toml` (see `example.index.toml`) for ordered path-glob rules.

### Example 1 — print a map to stdout

```bash
index --root ./my-workspace --json
```

Expected output (illustrative — paths, hashes, and timestamps vary):

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

### Example 2 — write a map file (default mode)

```bash
index --root ./my-workspace
```

Expected output (illustrative):

```text
wrote /path/to/my-workspace/INDEX.json
repos=2 dirty=0
```

The JSON file content matches the structure shown in Example 1.

### Example 3 — custom output path and worker count

```bash
index --root ./my-workspace --output ./inventory.json --jobs 8
```

Expected output (illustrative):

```text
wrote /path/to/inventory.json
repos=2 dirty=0
```

### Example 4 — use an explicit config

```bash
index --root ./my-workspace --config ./example.index.toml --json
```

Rules in the config are matched against each repo's workspace-relative path (first
match wins) before the remote-host fallback. A `--config` path that does not exist is a
fatal error (non-zero exit).

## Configuration (`.index.toml`)

Place a `.index.toml` at the workspace root (auto-discovered) or pass `--config PATH`.
Every section is optional; with no file, the neutral remote-host heuristic applies.

```toml
# Ordered classification rules — first match wins. `pattern` is matched against each
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

When no rule matches a repo, classification falls back to the remote host: no remote →
`local`, a public-hosting domain (`github.com`, `gitlab.com`, `bitbucket.org`,
`codeberg.org`, `git.sr.ht`) → `public`, otherwise → `private`. Credential-shaped material
in remote URLs is redacted in **every** mode; `portable = false` additionally emits
absolute paths and a `root` field and is meant only for maps that never leave the machine.

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

- `build_map(root: Path, config: Config, tool_version: str) -> Map` — scan and return
  the in-memory map.
- `write_map(root, config, tool_version, output: Path) -> Map` — same, but also writes
  pretty JSON to `output`.
- `load_config(path: Path | None, root: Path) -> Config` / `default_config() -> Config`.
- `classify(path: str, is_repo: bool, origin: str, config: Config) -> str`.
- `Map.to_json()` / `RepoRow.to_json()` — plain-dict serialization.

### Example — build a map in code

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

Expected output (illustrative):

```text
2 0
{'public': 1, 'local': 1}
proj-a public main eb4e19b
proj-b local main e4f1b0c
```

### Example — classify a single path

```python
from index_graph import classify, default_config

cfg = default_config()
classify("proj-a", True, "https://github.com/example/proj-a.git", cfg)  # -> "public"
classify("proj-b", True, "", cfg)                                       # -> "local"
```

## Dependency graph & context pack

`index` can infer a repo→repo dependency graph from real code and emit a
synthesis context pack with roles, relations, and extracted prose.

### `graph` subcommand

```text
index graph --root ROOT [--json]
```

| Flag     | Default           | Meaning                                                     |
| -------- | ----------------- | ----------------------------------------------------------- |
| `--root` | current directory | Workspace root to scan.                                     |
| `--json` | off               | Emit a JSON array of relation objects instead of text.      |

Edges are derived from Python (`pyproject.toml`, `setup.cfg`, source imports) and
JavaScript/TypeScript (`package.json`, source imports). Each edge carries the file (and
line) that witnesses it and a confidence grade:

- `high` — both a declared dependency and an observed import agree.
- `moderate` — a single signal (manifest-only or import-only).
- `low` — name is ambiguous (two different repos expose the same normalized name) or the
  target name is too short to resolve reliably.

#### Example — `graph --json` output shape

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

| Flag          | Default           | Meaning                                                         |
| ------------- | ----------------- | --------------------------------------------------------------- |
| `--root`      | current directory | Workspace root to scan.                                         |
| `--json`      | off               | Emit the context pack as JSON instead of Markdown.              |
| `--focus REPO`| —                 | Emit only the named repo's dependency neighbourhood (bidirectional closure). |
| `--audit`     | off               | Print only the salience-faithfulness audit (hubs + mismatches), not the pack. |

Exit codes:

- `0` — context pack written (or printed) successfully.
- `2` — `--focus <repo>` names a repo not found in the workspace; a near-match hint is
  printed to stderr.

The map subcommand (`index map`, or the legacy flat invocation
`index --root ...`) is unaffected.

### `viz` subcommand

```text
index viz --root ROOT [--format FORMAT] [--focus REPO] [--no-external] [--out PATH | --out-dir DIR]
```

| Flag           | Default           | Meaning                                                                  |
| -------------- | ----------------- | ---------------------------------------------------------------------- |
| `--root`       | current directory | Workspace root to scan.                                                |
| `--format`     | html              | Output format: `html`, `svg`, `mermaid`, or `all` (all formats + manifest metadata). |
| `--focus REPO` | —                 | Render only the named repo's dependency neighborhood (bidirectional closure). |
| `--no-external`| off               | Omit external (third-party) dependencies from the graph.               |
| `--out PATH`   | `<root>/graph.html` (or format-dependent) | Write a single format to a specific file path. |
| `--out-dir DIR`| `<root>/`         | Write all outputs to a directory.                                      |

#### Format details

- **html** (default): Self-contained interactive dashboard with drag/pan zoom, color-coded nodes,
  and bidirectional edge visibility. Opens directly from `file://` with no external URLs or
  runtime dependencies. Double-render of the same input produces byte-identical output.

- **svg**: Standalone SVG network graph (force-directed layout). Suitable for embedding or
  printing. Also self-contained and deterministic.

- **mermaid**: Mermaid flowchart markup (`.mmd`). Renders in GitHub markdown and online Mermaid
  editors. Deterministic but depends on Mermaid renderer to produce visual output.

- **all**: Writes `graph.html`, `graph.svg`, `graph.mmd`, `context.json`, and `context-manifest.json`.
  The manifest contains artifact paths and per-file content hashes (SHA-256) for auditing and
  downstream handoff (e.g., to a static site builder or asset verifier).

#### Example — render the full graph as HTML

```bash
index viz --root ./my-workspace
```

Expected output: writes `/my-workspace/graph.html`; open it in any browser from `file://`.

#### Example — render one repo's neighborhood as a Mermaid diagram

```bash
index viz --root ./my-workspace --focus my-app --format mermaid --out ./my-app-deps.mmd
```

#### Example — batch render all formats with manifest

```bash
index viz --root ./my-workspace --format all --out-dir ./viz-output
```

Expected: writes `viz-output/graph.{html,svg,mmd}`, `context.json`, and `context-manifest.json`.

## Notes

- This CLI is agent assisted. Review output before sharing it in public.
- Maps are portable by default: repo paths are root-relative, the absolute root is
  replaced by a short hash prefix, and credential-shaped material in remote URLs is
  redacted.
- The output schema is versioned (`schema_version: 1`).
