# Design: more ecosystems for `index` (Rust, Go, Java)

> Date: 2026-06-24
> Status: Approved in shape (brainstorming), pending spec review then plan.
> Repo: PUBLIC `index` (`HarperZ9/index`, PyPI `index-graph`), worktree `c:/dev/worktrees/wrm-rename`, branch `feat/v1.2-ecosystems` off the published 1.1.0.

## Summary

`index` builds a repo-to-repo dependency graph from evidence, but today it only understands Python and JavaScript/TypeScript. A Rust, Go, or Java developer who points it at their workspace sees their repos as isolated dots, because nothing reads their manifests or imports. This sprint adds three ecosystem resolvers, Rust (Cargo), Go (go.mod), and Java (Maven and best-effort Gradle), so those workspaces show real edges. It is a reach release: more communities can use the tool on their own code.

The work fits the existing resolver seam almost entirely. Each ecosystem is one small class. The only change outside the resolvers is a single, general enhancement to edge resolution that lets Go import paths match their module.

## Goal

When `index graph` (or `viz`, `context`, `atlas`) is run on a workspace of Rust, Go, or Java repos, the dependency edges between those repos appear, each carrying the file and line that witnesses it and a confidence grade, exactly as Python and JS edges do now.

## The resolver seam (existing, unchanged)

Every ecosystem implements the `Resolver` protocol in `graph/resolvers/base.py`:

- `matches(repo_root) -> bool`: is this a repo of my ecosystem?
- `exposed_names(repo_root) -> set[str]`: what is this repo called, so others can depend on it?
- `raw_edges(repo_root) -> list[RawEdge]`: what does it depend on or import, with the witnessing file and line?

`build_graph` calls every resolver, collects exposed names into an index, and `resolve_edges` matches each raw edge's target against that index (exact, after `normalize_name` lowercases and unifies `-`/`_`). An edge graded `high` has both a manifest and an import signal agreeing; `moderate` has one; `low` is ambiguous or too short. New resolvers are registered in `graph/resolvers/__init__.py`'s `ALL_RESOLVERS`. Nothing else in `build_graph`, the pack, or any renderer changes.

## The one core change: longest-prefix fallback for path-like targets

Python and JS dependency names match a repo's exposed name exactly. Go is different: a module is named `github.com/org/repo`, but code imports `github.com/org/repo/pkg/sub`, which is longer than the module. Exact matching cannot connect them.

`resolve_edges` gains a fallback: when a target name contains `/` and has no exact match in the index, try the longest exposed name that is a segment-aligned path prefix of the target. So an import of `github.com/org/repo/pkg` resolves to the repo whose module is `github.com/org/repo`. The fallback only fires when exact matching fails, only for slash-containing targets, and prefers the longest prefix, so it is safe for the existing resolvers (Python names have no slashes; JS scoped names like `@scope/pkg` are already trimmed to the package by the JS resolver before they reach resolution). A unit test locks the behavior.

## Per-ecosystem design

### Rust (Cargo)

- **matches:** a `Cargo.toml` exists in the repo (root or a workspace member).
- **exposed_names:** the `[package] name` of every `Cargo.toml` in the repo (a Cargo workspace has several crates). Parsed with stdlib `tomllib`.
- **raw_edges:**
  - manifest: the keys of `[dependencies]`, `[dev-dependencies]`, and `[build-dependencies]` in each `Cargo.toml`. A path dependency (`foo = { path = "../foo" }`) still names the crate, so it matches.
  - import: a scan of `.rs` files for `use <crate>::...` and `extern crate <crate>;`, taking the leading path segment as the crate name and excluding the `crate`, `self`, and `super` keywords (which refer to the current crate, not a dependency). Rust source uses `_` where `Cargo.toml` uses `-`; `normalize_name` already unifies them. Stdlib roots like `std` and `core` simply find no workspace match and drop out.
- **confidence:** high when a declared dependency and a `use` agree.

### Go (go.mod)

- **matches:** a `go.mod` exists.
- **exposed_names:** the `module` path from `go.mod` (for example `github.com/org/repo`).
- **raw_edges:**
  - manifest: every `require` path in `go.mod`, single-line and block form. These are module paths, matched exactly.
  - import: `import "path"` lines (single and grouped) in `.go` files. The import path is matched by the longest-prefix fallback above, so an import of a sub-package of another repo's module resolves to that repo.
- **confidence:** high when a `require` and an `import` of the same module agree.
- `go.mod` is not TOML; it is a small line-oriented format, parsed directly (no dependency).

### Java (Maven and best-effort Gradle)

- **matches:** a `pom.xml`, `build.gradle`, or `build.gradle.kts` exists.
- **exposed_names:** the module's `groupId:artifactId`. For Maven, read `<groupId>`/`<artifactId>`, falling back to `<parent><groupId>` when a child pom omits its own group (Maven inheritance). For Gradle, best-effort from `group` and the project/`rootProject.name`.
- **raw_edges (manifest only):**
  - Maven: each `<dependency>`'s `groupId:artifactId`, parsed with stdlib `xml.etree.ElementTree`.
  - Gradle: a regex scan for `implementation`/`api`/`compileOnly`/`testImplementation` of `'group:artifact:version'` or `("group:artifact:version")`, and `project(':module')` for inter-module dependencies. Marked best-effort.
- **no import scan:** Java imports name packages, not artifacts, and there is no manifest-derived package-to-artifact map, so import matching would be unreliable. Java edges are therefore moderate confidence.

## Constraints

- **Zero runtime dependencies.** Stdlib only: `tomllib` (Cargo), `xml.etree.ElementTree` (Maven), line and regex parsing (go.mod, Gradle, Rust/Go imports). The boundary tests stay green.
- **Deterministic.** Sorted collections; same workspace gives the same graph.
- **Backward compatible.** Purely additive. The four existing edge fields and all pack keys are unchanged; Python and JS edges resolve identically. The prefix fallback only changes results for targets that have no exact match today.
- **No regression.** The existing suite stays green; each ecosystem adds its own tests.

## Known limitations (honest bounds)

- **Rust workspaces:** crates are discovered by walking for `Cargo.toml`; virtual manifests and renamed dependencies (`package = "..."`) are read literally, edge cases noted not deep-handled.
- **Go:** nested modules (more than one `go.mod`) are uncommon; the resolver treats the repo's root `go.mod` as the module. `replace` directives that point at local paths are not specially resolved; the `require` path still matches by name.
- **Java group inheritance:** handled one level (child reads `<parent><groupId>`); deeper or property-interpolated coordinates (`${project.groupId}`) are left literal.
- **Gradle:** best-effort by design. Version catalogs (`libs.foo`), dynamic configuration, and Kotlin DSL indirection can be missed. Documented as such.
- **Untrusted XML:** `pom.xml` is parsed with `xml.etree.ElementTree`, catching parse errors, and external entities are not resolved. A hostile local pom could still attempt internal-entity expansion, a low-severity scan-time DoS given that you are scanning your own workspace; noted, not specially defended.

## Testing

Mirror the existing `tests/test_resolver_python.py` and `tests/fixtures/py-app`, `py-lib` pattern. For each ecosystem, one tiny two-repo fixture where `a` depends on `b`:

- `exposed_names` returns the expected crate/module/coordinates.
- manifest edges are derived with the right witnessing file.
- import edges are derived (Rust, Go) with file and line.
- end-to-end through `build_graph`: the cross-repo edge appears with the expected confidence.
- a focused unit test for the longest-prefix fallback (a Go-style import resolving to a module prefix, and a no-false-positive case).

## Success criteria

1. `index graph --root <rust-ws>` (and Go, and Java) shows the inter-repo edges, each with evidence and a confidence grade.
2. Rust and Go agreeing edges are `high`; Java manifest edges are `moderate`.
3. The longest-prefix fallback resolves Go imports to their module and does not change any existing Python or JS result.
4. Zero runtime dependencies; the boundary and determinism tests stay green; each ecosystem adds tests with real fixtures.
5. `map`, `graph`, `context`, `viz`, `atlas`, and their JSON are otherwise unchanged.

## Release

Ships as `index-graph` 1.2.0, with a `CHANGELOG.md` entry (the 1.1.0 entry, missing from the last release, is added in the same pass). Publish stays operator-gated.

## Phasing (one plan, in order)

1. The longest-prefix fallback in `resolve_edges`, with its unit test (the enabling core change, smallest and most central).
2. Rust resolver + fixtures + tests.
3. Go resolver + fixtures + tests (depends on phase 1 for import edges).
4. Java resolver (Maven, then best-effort Gradle) + fixtures + tests.
5. `CHANGELOG.md` (1.1.0 and 1.2.0 entries) and the version bump to 1.2.0.
