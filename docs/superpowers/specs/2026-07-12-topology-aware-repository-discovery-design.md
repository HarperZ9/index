# Topology-Aware Repository Discovery Design

**Status:** Operator-approved design

**Date:** 2026-07-12

## Goal

Make Index report physical Git worktrees rather than filesystem aliases, while preserving legitimate linked worktrees, submodules, separate Git directories, and sole mounted aliases.

## Problem

Index currently treats any directory containing a `.git` directory or file as a repository. Two verified topology artifacts inflate the workspace map:

- a release-audit source copy contains a copied `.git` file pointing at the administrative directory of a different registered Calibrate Pro worktree, producing 87 phantom tracked changes;
- `C:/dev/aleph` is a junction to `C:/dev/opsec`, so the same working tree is reported twice.

The saved workspace snapshot reports 195 repository paths and 116 tracked status rows. Removing only the copied worktree pointer and duplicate junction yields 191 physical rows and 25 tracked status rows. Configuration and metric semantics did not cause the jump.

## Design

Topology validation happens at the discovery boundary so CLI, MCP, Python API, graph, freshness, and invalidation consumers receive the same accepted repository set.

### Physical identity

For each discovered candidate, compute a conservative physical identity with normalized `realpath(abspath(path))`. If canonicalization fails, retain the lexical path.

When multiple candidates share one physical identity:

1. prefer a direct path whose lexical absolute path already equals its real path;
2. otherwise prefer the lexically first relative path;
3. retain only that representative.

A sole alias remains visible. This preserves workspaces mounted through one junction while removing duplicate aliases when both target and alias are under the scan root.

### Linked-worktree pointer validation

For a `.git` file:

1. parse its `gitdir:` target, supporting absolute and relative paths;
2. if the target administrative directory contains Git's linked-worktree `gitdir` backlink, compare that backlink to the candidate's `.git` marker using canonical normalized paths;
3. accept only an exact match;
4. on mismatch, skip the copied/unregistered marker and emit a warning with `git worktree repair` guidance.

Accept `.git` directories. Accept `.git` files whose administrative directories have no linked-worktree backlink; this preserves submodules, separate Git directories, legacy layouts, and existing lightweight test fixtures.

Never deduplicate by remote URL, branch, HEAD, or common Git directory. Legitimate linked worktrees intentionally share those values.

## Interfaces

- `index_graph.gitmeta`: pure `.git` pointer/backlink parser and validator.
- `index_graph.scan.discover_repos`: canonical physical grouping, deterministic representative selection, and pointer validation.
- Map schema and command-line output remain unchanged.
- Discovery warnings provide evidence for skipped copied pointers without exposing remote credentials.

## Error Handling

- `realpath` or permission failure falls back to lexical identity.
- Malformed or unreadable marker files retain the candidate under the current degrade-not-crash contract.
- A mismatched linked-worktree backlink is the one fail-closed case because it proves the marker belongs to another working tree.
- Warning output is Unicode-safe and contains paths only.

## Test Design

Tests are written before implementation and must fail for the observed behavior.

### Git metadata tests

- matching absolute backlink is accepted;
- matching relative backlink is accepted;
- copied pointer with mismatched backlink is rejected;
- `.git` file without a backlink is retained;
- unreadable or malformed marker degrades without crashing.

### Discovery tests

- canonical worktree and copied audit marker retain only the canonical worktree;
- direct directory and junction/symlink alias retain the direct path;
- sole alias remains visible;
- distinct legitimate linked worktrees remain distinct;
- order remains deterministic;
- existing prune behavior remains unchanged.

### Workspace acceptance

Run Index against `C:/dev` and verify:

- the release-audit source copy is absent;
- `C:/dev/opsec` appears once and `C:/dev/aleph` is not duplicated;
- the real Calibrate Pro worktree remains present and clean;
- saved-snapshot-equivalent tracked count is 25, subject only to independently changed real repositories;
- no legitimate linked worktree or submodule disappears.

## Documentation

`USAGE.md` documents physical-path deduplication and linked-worktree validation. `CHANGELOG.md` records the correctness fix. No config or schema migration is required.

## Non-Goals

- No blanket pruning of `release-audits`, junctions, scratch, or worktrees.
- No deletion of audit evidence.
- No Git repair or cleanup performed by Index.
- No new topology schema in this urgent correction.

## Success Criteria

- The two reproduced inflation cases have failing regression tests before code changes.
- Targeted and full Index tests pass after the minimal implementation.
- CLI, MCP, and Python discovery use the same filtered set.
- A fresh workspace map reports only physical repositories and real tracked state.

