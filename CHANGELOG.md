# Changelog

## 1.0.0

Renamed to **index** (`pip install index-graph`, command `index`); flagship release. (Was `workspace-repo-map`.)

## 0.4.0

- Add `viz` subcommand: render the dependency graph as a self-contained interactive
  HTML dashboard (default), a standalone SVG network graph, or a Mermaid flowchart.
- `viz --format all` also emits `context.json` and a `context-manifest.json` handoff
  (artifact paths + content hashes) for downstream consumers.
- Renders are deterministic (byte-identical for identical input) and self-contained
  (no external URLs, no runtime dependencies).

## 0.3.0

### Added
- `graph` subcommand: infer a repo→repo dependency graph from Python and
  JavaScript/TypeScript manifests and source imports. Every edge carries its
  evidence (witnessing file/line + signal kind) and a confidence grade.
- `context` subcommand: render a synthesis context pack (structural roles +
  relations + extracted prose) with a salience-faithfulness audit and a
  `--focus <repo>` neighborhood closure.

### Changed
- The CLI now uses subcommands (`map`, `graph`, `context`). The previous flat
  invocation (`workspace-repo-map --root ...`) is preserved and dispatches to `map`.
- Makes generated repository maps portable by default.
- Replaces absolute local root paths with a root hash prefix.
- Omits protected remotes and redacts credential-shaped remote URL material.

## 0.2.0 - 2026-06-18

- Config-driven classification via optional `.repomap.toml` (ordered path-glob rules,
  neutral remote-host fallback). Personal taxonomy moves to user config.
- Unifies the CLI into a single argument parser; removes the duplicate.
- Adds a stable public API (`__all__`, `__version__`) and a versioned output
  (`schema_version: 1`); drops the duplicated `relative` field and protected-specific
  counts in favor of generic `class_counts`.
- Parallelizes per-repo git calls; output remains deterministic.
- Adds a portable (default) / local output mode and an `annotations` passthrough.
- Raises the Python floor to 3.11 (stdlib `tomllib`); runtime dependencies stay empty.

## 0.1.0 - 2026-06-13

- Initial public release candidate.
- Ships compact JSON repository inventory mapping for multi-repo local
  workspaces.
- Adds Python package metadata, CI, license, authorship, and contribution
  boundary files.
