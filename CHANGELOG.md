# Changelog

## Unreleased

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
