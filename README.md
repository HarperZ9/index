# Workspace Repo Map

> Compact JSON repository inventory maps for multi-repo workspaces.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.3.0-informational.svg)
[![CI](https://github.com/HarperZ9/workspace-repo-map/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/workspace-repo-map/actions/workflows/ci.yml)
![deps: none](https://img.shields.io/badge/deps-none-success.svg)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

`workspace-repo-map` scans a workspace root for Git repositories and writes a
compact JSON map of remotes, branches, dirty counts, marker files, and public or
local-only classification hints.

Generated maps are portable by default: repository paths are root-relative, the local
root is represented by a short hash, and credential-shaped material in remote URLs is
always redacted. Dropping whole origins by class is opt-in via `.repomap.toml`.

## Install

```bash
python -m pip install workspace-repo-map
```

## Usage

```bash
workspace-repo-map --root . --output WORKSPACE-REPO-MAP.json
workspace-repo-map --json
```

Without `--json`, the map is written to `<root>/WORKSPACE-REPO-MAP.json` (or `--output`)
and a one-line summary (`wrote <path>` / `repos=N dirty=M`) is printed.

Classification is driven by an optional `.repomap.toml` at the workspace root (see
`example.repomap.toml`). With no config, repos are classified by a neutral remote-host
heuristic: `local` (no remote), `public` (origin on a public host), or `private`. Here
`public` means "origin is on a public code-hosting platform" — a heuristic, not a
guarantee of visibility.

For a full install line, the complete flag list, the importable Python API, and worked
examples with expected output, see [USAGE.md](USAGE.md). A runnable end-to-end demo lives
in [`examples/demo.py`](examples/demo.py).

## Dependency graph & context pack

Beyond the inventory map, `workspace-repo-map` infers how the repos in a workspace
depend on each other — from real code, with evidence on every edge.

```bash
workspace-repo-map graph --root .                  # repo→repo dependency graph (text)
workspace-repo-map graph --root . --json           # ... as JSON; each edge carries its witness
workspace-repo-map context --root .                # synthesis pack: roles + relations + prose
workspace-repo-map context --root . --focus <repo> # one repo's dependency neighborhood
workspace-repo-map viz --root .                    # render the graph as an interactive HTML dashboard, SVG, or Mermaid
```

Edges are derived from Python and JavaScript/TypeScript manifests and source imports;
each carries the file (and line) that witnesses it and a confidence grade
(`high` when both a declared dependency and an observed import agree). See
[USAGE.md](USAGE.md) for the full reference.

## Notes

- This CLI is agent assisted. Review output before sharing it in public.
- Repository names and branch details are exported from local git metadata.
- Absolute local root paths are not included by default.

---
**Zain Dana Harper** — small tools with explicit edges.
[Portfolio](https://harperz9.github.io) · [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>
