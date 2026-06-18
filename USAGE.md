# Usage

`workspace-repo-map` scans a workspace root for Git repositories and emits a compact
JSON inventory map. It ships a CLI (`workspace-repo-map`) and a small importable Python
API. Runtime dependencies: none. Python: 3.11+.

## Install

```bash
python -m pip install workspace-repo-map
```

Or from a checkout (editable):

```bash
python -m pip install -e .
```

## CLI

The console script is `workspace-repo-map` (equivalently `python -m workspace_repo_map`).

```text
workspace-repo-map [--root ROOT] [--output OUTPUT] [--json]
                   [--config CONFIG] [--jobs JOBS] [--version]
```

| Flag        | Default                          | Meaning                                              |
| ----------- | -------------------------------- | ---------------------------------------------------- |
| `--root`    | current directory                | Workspace root to scan.                              |
| `--output`  | `<root>/WORKSPACE-REPO-MAP.json` | Output path (ignored when `--json` is given).        |
| `--json`    | off                              | Print the JSON map to stdout instead of writing it.  |
| `--config`  | `<root>/.repomap.toml` if present | Path to a `.repomap.toml`. Missing explicit path is fatal. |
| `--jobs`    | config / CPU heuristic           | Override the parallel git worker count (must be ≥ 1).|
| `--version` | —                                | Print `workspace-repo-map 0.2.0` and exit.           |

Classification with no config falls back to a remote-host heuristic: `local` (no
remote), `public` (origin host in the known public set), or `private`. Supply a
`.repomap.toml` (see `example.repomap.toml`) for ordered path-glob rules.

### Example 1 — print a map to stdout

```bash
workspace-repo-map --root ./my-workspace --json
```

Expected output (illustrative — paths, hashes, and timestamps vary):

```json
{
  "schema_version": 1,
  "tool_version": "0.2.0",
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
workspace-repo-map --root ./my-workspace
```

Expected output (illustrative):

```text
wrote /path/to/my-workspace/WORKSPACE-REPO-MAP.json
repos=2 dirty=0
```

The JSON file content matches the structure shown in Example 1.

### Example 3 — custom output path and worker count

```bash
workspace-repo-map --root ./my-workspace --output ./inventory.json --jobs 8
```

Expected output (illustrative):

```text
wrote /path/to/inventory.json
repos=2 dirty=0
```

### Example 4 — use an explicit config

```bash
workspace-repo-map --root ./my-workspace --config ./example.repomap.toml --json
```

Rules in the config are matched against each repo's workspace-relative path (first
match wins) before the remote-host fallback. A `--config` path that does not exist is a
fatal error (non-zero exit).

## Configuration (`.repomap.toml`)

Place a `.repomap.toml` at the workspace root (auto-discovered) or pass `--config PATH`.
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
from workspace_repo_map import (
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
from workspace_repo_map import build_map, default_config, __version__

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
from workspace_repo_map import classify, default_config

cfg = default_config()
classify("proj-a", True, "https://github.com/example/proj-a.git", cfg)  # -> "public"
classify("proj-b", True, "", cfg)                                       # -> "local"
```

## Notes

- This CLI is agent assisted. Review output before sharing it in public.
- Maps are portable by default: repo paths are root-relative, the absolute root is
  replaced by a short hash prefix, and credential-shaped material in remote URLs is
  redacted.
- The output schema is versioned (`schema_version: 1`).
