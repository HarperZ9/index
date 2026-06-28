# Changelog

## Unreleased

- Enterprise readiness: adds `docs/ENTERPRISE-READINESS.md` for context envelopes, action receipts, readability gates, and host-neutral operation.
- Operator surface: the status payload now advertises shared Project Telos CLI/MCP/plugin/IDE/TUI/app contracts for enterprise, research, creative, scientific, and education workflows.

Presentation and operator-surface housekeeping for Project Telos parity.

- README: uses the shared five-flagship navigation, fixes the CI badge to the current `HarperZ9/index` repository, and adds a current-status block.
- Status payload: exposes current operator commands, MCP tool names, and the 2.8 capability summary under `native`.
- MCP tools: records native availability for `index.map`, `index.context`, `index.status`, and `index.doctor` alongside the existing graph/focus/verify/router/internals tools.
- Operator commands: documents `index status --json`, `index doctor --json`, and `index demo --json` as part of the shared Project Telos action envelope.
- Router: carries the first dependency signal into generated workspace maps, so compact `AGENTS.md`/`CLAUDE.md` output names the file and line behind each internal edge.

## 2.8.0

### Added
- `index bench`: a token-economics benchmark you can reproduce on your own workspace.
  It measures the bytes index reads (the manifests and sources of every ecosystem) against
  the bytes of the one structural pack it emits, and reports the reduction. Bytes are exact
  and model-agnostic; the token figures use the common ~4 bytes/token approximation, and
  the reduction ratio is independent of that constant, so the headline number does not
  depend on any tokenizer. `--json` emits a re-checkable `index.bench/1` report. This turns
  the "a structural map is cheaper than reading the code" thesis into a number you verify
  rather than trust. On a 47-repo, ~50 MB reference workspace the structural pack came back
  roughly 70x smaller than the source it distills.

### Notes
- Additive and backward compatible. Zero new dependencies. The benchmark reuses the same
  relevant-file walk as the freshness fingerprint, so it counts exactly what the graph reads.

## 2.7.0

### Added
- Content freshness: a certificate can now know when the ground truth moved under it.
  `index check --freshness` stamps the certificate with a deterministic per-repo
  content fingerprint (a SHA-256 over the graph-relevant files of all nine ecosystems).
  `index freshness --cert CERT --root ROOT` recomputes the workspace fingerprint and
  returns FRESH, STALE (naming the repos added, removed, or changed), or UNVERIFIABLE
  (the certificate carries no stamp), with exit codes 0/1/2. This is the mid-loop "has
  anything changed since I verified?" check, re-checkable like every index verdict.
- The fingerprint is conservative by construction: it may report STALE for a content
  change that does not alter the resolved graph, but it never reports FRESH when a
  graph-relevant file changed. The relevant-file set is declared by the resolvers
  themselves, so a new ecosystem is covered automatically.

### Notes
- Additive and backward compatible. Zero new dependencies. A certificate minted without
  `--freshness` is byte-identical to one from 2.6.0 (the `freshness` key is present only
  when asked).

## 2.6.0

### Added
- Four new ecosystem resolvers, widening dependency reach from five languages to nine with
  no new runtime dependency: C# (`.csproj` PackageReference and ProjectReference, plus
  `using`), Ruby (Gemfile gems and `require`/`require_relative`, gemspec name), PHP
  (`composer.json` require and `use` namespaces), and C/C++ (CMake `project`,
  `add_library`, `target_link_libraries`, and `#include`, best-effort). Each follows the
  existing manifest-plus-import evidence pattern.

### Notes
- Additive and backward compatible. Zero new dependencies, standard library only.

## 2.5.0

### Added
- `index mcp`: a zero-dependency, MCP-shaped stdio protocol face. Newline-delimited
  JSON-RPC 2.0 over stdin/stdout (no SDK, no model) speaking `initialize`, `tools/list`,
  and `tools/call`, with five deterministic tools (`index_graph`, `index_focus`,
  `index_verify`, `index_router`, `index_internals`). An agent host or orchestrator
  connects and consumes index's verified map natively. The protocol pillar, not embeddings.

### Notes
- Additive and backward compatible. Zero new dependencies.

## 2.4.0

### Added
- `index verify`: a deterministic claim-grounding oracle. `--depends "A -> B"` or
  `--exists NAME` grounds the claim against the real graph and returns MATCH (with the
  file:line evidence), REFUTED, or UNVERIFIABLE, its own honest triad. Re-checkable
  (schema `index.verification/1`, a content hash plus a recheck command), with distinct
  exit codes 0/1/2. The anti-hallucination check: a model confirms a dependency against
  the graph instead of trusting its memory.

### Notes
- Additive and backward compatible. Zero new dependencies.

## 2.3.0

### Added
- `index router`: a deterministic, evidence-carrying workspace map for CLAUDE.md / AGENTS.md.
  Renders entry points, the depended-on core, where each repo lives with its role and
  dependencies, and which docs describe what, from the dependency graph and the docs atlas.
  Re-runnable; replaces the hand-maintained index/read-first/brief.
- `index context --focus` gains `--hops N` (a k-hop-bounded neighborhood) and emits a
  preservation manifest: the focus, the hop bound, the kept node count, and the boundary
  edges and nodes it dropped. A compact pack now declares its losses instead of reading as
  complete (the information-bottleneck discipline).

### Notes
- Additive and backward compatible. Zero new dependencies.

## 2.2.0

### Added
- Required-edge conformance. The `[architecture]` block gains `require` rules: intended
  dependencies that must exist. `index check` reports an `absence` finding (DRIFT) when a
  required edge between two existing repos is not realized, and `require_unmatched`
  (UNVERIFIABLE) when a rule names a repo not in the workspace, mirroring an unmatched
  layer. With the existing forbidden-edge and layer checks (divergence), this completes the
  Reflexion-model conformance triad: convergence, divergence, and absence. An empty
  `require` leaves the criterion hash byte-identical to 2.1.0.

### Notes
- Additive and backward compatible. Zero new dependencies.

## 2.1.0

### Added
- Soundness-typed coverage on the module graph. `index internals` and the `index check`
  certificate now report what the static scan could not verify: files it failed to parse,
  and dynamic imports (`importlib.import_module`, `__import__`, `require` of a variable).
  A certificate is now honest about its soundness scope instead of implying completeness.
  `internals --json` carries a `coverage` object; the certificate carries an optional
  `coverage` field naming the repos with unverifiable regions. Grounded in the call-graph
  soundness literature: a static tool cannot see dynamic dispatch, so it says so.

### Notes
- Additive and backward compatible. Zero new dependencies. `extract_internal_edges` keeps
  its signature.

## 2.0.0

### Added
- `index internals`: an intra-repo module dependency graph, so the map sees inside a
  repo and not only repo as atom. Python is AST-exact; JavaScript/TypeScript, Rust, and
  Go are best-effort and file-level. Reports internal cycles and per-module fan-in and
  fan-out.
- `[architecture]` config block in `.index.toml`: declare ordered layers, forbidden
  edges, a cycle ceiling (`max_cycles`), and ownership globs. A criterion the tool can
  measure real structure against.
- `index check`: evaluate the graph against the declared criterion. Every violation
  carries evidence to the file and line. Exits non-zero when findings exist, so it gates
  CI.
- `index snapshot` and `index drift`: write a canonical, byte-stable snapshot, then diff
  two snapshots into added and removed repos and edges, introduced and cleared cycles,
  and role changes.
- A re-checkable certificate for `check` and `drift`: a content hash, a criterion hash,
  and one of three verdicts, MATCH, DRIFT, or UNVERIFIABLE, never a fourth. A consumer
  re-runs the `recheck` command and confirms the verdict from the evidence, rather than
  trusting it. The seam is specified in `docs/PROTOCOL.md`.

### Notes
- Additive and backward compatible: `map`, `graph`, `context`, `viz`, and `atlas` and
  their JSON are unchanged. Zero new runtime dependencies. The tool runs fully offline,
  with no API, no account, and no model required, and is agnostic to whatever produced
  the code it reads.
- `.index.toml` is now read tolerantly of a UTF-8 byte-order mark.

## 1.2.0

### Added
- Rust (`Cargo.toml`), Go (`go.mod`), and Java (Maven `pom.xml`, best-effort Gradle)
  dependency resolvers. Workspaces in these ecosystems now show inter-repo edges, each
  with evidence and a confidence grade. Rust and Go reach `high` confidence when a
  manifest and an import agree; Java is manifest-only (`moderate`).

### Changed
- `resolve_edges` gains a longest-prefix fallback for path-like dependency names, so a
  Go import of a module's sub-package resolves to that module. Python and JavaScript
  resolution is unchanged.

## 1.1.0

### Added
- `index atlas`: a two-layer code-and-knowledge map. Markdown docs become first-class
  nodes joined to the code they describe, rendered as one self-contained, navigable HTML
  dashboard (pan and zoom, unified repo and doc search, in-place rendered markdown with
  clickable `[[wiki-links]]`, focus, and a navigation trail).
- Dependency dashboard: cycle detection and highlighting, edge-evidence tooltips, a
  legend, and neighborhood highlighting. `index graph --cycles` reports dependency cycles.

### Changed
- License moved to fair source (FSL-1.1-MIT): source-available with a competing-use
  restriction, converting to MIT two years after each release. 1.0.0 remains MIT.

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
