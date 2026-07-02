# Index protocol

This document specifies the two machine-readable artifacts `index` emits for downstream
consumers: the **snapshot** and the **certificate**. Both are plain JSON. Any consumer
can read them, and any consumer can verify a certificate by recomputing its hashes and
re-running its command. The protocol names no other tool and assumes none. A consumer may
be a CI job, a code reviewer, or an automated agent.

The tool that produces these artifacts runs fully offline. It requires no network, no
account, no API key, and no model. It reads source code and emits JSON, and it is
agnostic to whatever produced the code and to whatever consumes the result.

## Canonical hashing

Every hash in this protocol is computed the same way. Serialize the object to canonical
JSON, then take its SHA-256:

```python
import hashlib, json
def canonical_sha(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
```

Canonical JSON sorts keys and uses compact separators, so the hash depends on the content
and not on key order or whitespace. Re-serializing the same content on any platform yields
the same hash.

## The snapshot: `index.snapshot/1`

A snapshot is the minimal, sorted projection of a dependency graph, written so two
snapshots can be diffed and so a snapshot is byte-stable across runs.

```json
{
  "schema": "index.snapshot/1",
  "repos": ["api", "core", "web"],
  "edges": ["api -> core", "web -> api"],
  "roles": {"api": ["entrypoint"], "core": ["library"], "web": []},
  "cycles": []
}
```

| Field | Meaning |
|-------|---------|
| `repos` | sorted repo names present in the graph |
| `edges` | sorted internal dependency edges, each `"from -> to"` |
| `roles` | repo name to its sorted structural roles |
| `cycles` | sorted dependency cycles, each a sorted list of repo names |

`index snapshot --root ROOT --out FILE` writes one. `index drift --from OLD --to NEW`
diffs two of them into added and removed repos and edges, introduced and cleared cycles,
and role changes.

## The certificate: `index.certificate/1`

A certificate is the verdict of a `check` or a `drift`, written so a consumer can confirm
it independently.

```json
{
  "schema": "index.certificate/1",
  "tool_version": "2.0.0",
  "kind": "check",
  "content_sha256": "<canonical_sha of the graph or snapshot pair>",
  "criterion_sha256": "<canonical_sha of the declared criterion, or null>",
  "verdict": "MATCH",
  "findings": [
    {"rule": "layer", "detail": "...", "edge": "core -> web", "evidence": "core/db.py:12"}
  ],
  "recheck": "index check --root . --internals --json"
}
```

| Field | Meaning |
|-------|---------|
| `kind` | `check` or `drift` |
| `content_sha256` | the hash of the artifact the verdict is about |
| `criterion_sha256` | the hash of the declared criterion, or `null` when none was declared |
| `verdict` | one of `MATCH`, `DRIFT`, `UNVERIFIABLE` |
| `findings` | the itemized reasons for a non-MATCH verdict, each with evidence where known |
| `recheck` | the exact command that reproduces this certificate |

### The three verdicts

There are three answers and there is no fourth. There is deliberately no `TRUSTED`.

- **MATCH**: the artifact satisfies the criterion.
- **DRIFT**: it does not. Every breach is listed in `findings` with the file and line
  that witnesses it.
- **UNVERIFIABLE**: the criterion cannot be evaluated against this artifact. No criterion
  was declared, or a declared layer names a repo that does not exist, or a rule needs a
  granularity the tool cannot resolve for the languages present. UNVERIFIABLE stops and
  says why. It is not a failure and it is not a pass. It is the honest answer when an
  answer cannot be earned.

### Coverage (optional)

When a check runs with `--internals`, the certificate carries a `coverage` object stating
what the module scan could and could not verify:

```json
"coverage": {
  "complete": false,
  "unverifiable_repos": {
    "myrepo": {
      "parse_errors": ["pkg/broken.py"],
      "dynamic_imports": [{"file": "pkg/loader.py", "line": 12}]
    }
  }
}
```

`complete` is true when every module parsed and every import resolved statically. When it
is false, `unverifiable_repos` names the files the scan could not parse and the dynamic
imports it could not follow (`importlib.import_module`, `__import__`, `require` of a
variable). This is the honest scope of the verdict: a static tool cannot see dynamic
dispatch, so the certificate says so rather than implying the graph is complete. Read a
MATCH as "no violation found in the structurally verifiable portion", not "proven
complete". `index internals --json` carries the same coverage detail per repo.

### Freshness (optional)

When a check runs with `--freshness`, the certificate carries a `freshness` stamp: a
content fingerprint of the workspace at mint time.

```json
"freshness": {
  "schema": "index.freshness/1",
  "root": "<sha256 fold of the per-repo fingerprints>",
  "repos": {"myrepo": "<sha256 over its graph-relevant files>"}
}
```

A repo fingerprint is a SHA-256 over the sorted `(relative-path, file-sha256)` pairs of
every graph-relevant file in the repo: the manifests and source suffixes the resolvers
read, across all ecosystems. It is deterministic and platform-independent. It is
conservative: a change to a relevant file always moves it, but a change to an irrelevant
file (a README, a note) does not, so STALE may be a false alarm while FRESH is never a
false assurance. The relevant-file set is the union of each resolver's declared
`fingerprint_names`, `fingerprint_suffixes`, and `fingerprint_globs`, so a new ecosystem
is covered without changing this schema.

`index freshness --cert CERT --root ROOT` recomputes the live workspace fingerprint and
compares it to the stamp, emitting a re-checkable report:

```json
{
  "schema": "index.freshness-report/1",
  "verdict": "STALE",
  "stamp_root": "<the certificate's freshness.root>",
  "current_root": "<the live fold>",
  "repos_added": [], "repos_removed": [], "repos_changed": ["myrepo"],
  "recheck": "index freshness --cert \"cert.json\" --root \".\""
}
```

The verdict is `FRESH` (the folds match), `STALE` (they do not; the deltas name the
repos), or `UNVERIFIABLE` (the certificate carries no freshness stamp). The command exits
0, 1, or 2 to match. This is a freshness verdict, a separate axis from the conformance
verdict above: a certificate can be a perfectly valid MATCH and also STALE, meaning the
structure it proved was correct then but the workspace has since moved.

The fingerprint tracks the files that determine the dependency graph, not every byte the
certificate hashes. A repo's free-text description, read from its README, is part of the
certificate's `content_sha256` but not the fingerprint, so editing only a README changes
the content hash that `recheck` recomputes while `freshness` still reports FRESH. The two
ask different questions on purpose. `recheck` asks whether this exact certificate
reproduces, byte for byte. `freshness` asks whether the structure it verified has moved.
For the dependency graph itself, FRESH is never a false assurance.

### How to verify a certificate

You do not trust a certificate. You re-run it.

1. Run the `recheck` command in the same workspace.
2. Recompute `content_sha256` and `criterion_sha256` from the fresh result with the
   canonical hash above.
3. Confirm the `verdict` matches.

If the hashes and the verdict agree, the certificate held. If they do not, the structure
or the criterion changed, which is itself the signal.

## The invalidation report: `index.invalidation/1`

Freshness says that the workspace moved. The invalidation report says what that movement
invalidates. It compares a pin, recorded earlier, against the current tree, and lands every
fingerprinted artifact or scope in exactly one of two buckets.

The pin (`index.invalidation-pin/1`) records the per-file SHA-256 of every graph-relevant
file per repo (the same relevant-file set the freshness fingerprint walks), the root docs
the context pack reads (the README family, which feed repo descriptions), and the
`index.snapshot/1` of the moment. Its `pinned_ref` is the canonical hash of that state,
computed with the hashing rule above. `index invalidate --root ROOT --out PIN` writes one.

`index invalidate --root ROOT --pin PIN [--json]` recomputes the same state from the live
tree and emits the report:

```json
{
  "schema": "index.invalidation/1",
  "pinned_ref": "<canonical hash of the pinned state>",
  "current_ref": "<canonical hash of the live state>",
  "verdict": "STALE",
  "invalidated": [
    {"artifact_or_scope": "certificate", "reason_code": "doc-changed", "evidence": ["README.md"]},
    {"artifact_or_scope": "context-pack", "reason_code": "doc-changed", "evidence": ["README.md"]},
    {"artifact_or_scope": "repo:app", "reason_code": "doc-changed", "evidence": ["README.md"]}
  ],
  "still_valid": ["graph-snapshot", "repo:lib"],
  "counts": {"scope": 5, "invalidated": 3, "still_valid": 2},
  "recheck": "index invalidate --root ROOT --pin PIN --json"
}
```

The scope is fixed by the pin: the three derived artifacts index fingerprints
(`certificate`, `context-pack`, `graph-snapshot`) plus one `repo:NAME` entry per pinned
repo. The counts must reconcile: `invalidated + still_valid == scope`, always.

Reason codes form a closed set, and a consumer must reject any other:

| Code | Meaning |
|------|---------|
| `file-changed` | a pinned graph-relevant file's content moved |
| `file-removed` | a pinned graph-relevant file is gone |
| `dependency-edge-changed` | the structural snapshot (edges, roles, cycles) moved |
| `doc-changed` | a pinned doc the context pack reads moved |
| `unversioned` | content is now in scope that the pin never versioned |

The report is sharper than the freshness fold on purpose. A README edit invalidates the
certificate and the context pack (their content hashes cover repo descriptions) but leaves
`graph-snapshot` in `still_valid`, because the structural projection does not read prose.
The verdict is `FRESH` (nothing invalidated) or `STALE`; a document that is not a pin
yields `UNVERIFIABLE` rather than a guess, and a tampered pin hash simply reads as a moved
file (STALE, `file-changed`), never a crash.

A consumer does not trust the ledger either. `reconcile_invalidation` re-derives it from
the report itself and turns any gap to DRIFT: a forged count, an unknown reason code, a
scope booked in both buckets, or a verdict that disagrees with its own lists.

## Module resolution bounds

The intra-repo module graph (`index internals`, and `index check --internals`) is exact
for some languages and best-effort for others. The bounds are stated, not hidden.

| Language | Resolution | Notes |
|----------|------------|-------|
| Python | AST-exact | relative and absolute internal imports, read from the syntax tree |
| JavaScript, TypeScript | best-effort, file-level | relative specifiers resolve to files; bare specifiers are external; dynamic and aliased imports may be missed |
| Rust | best-effort, file-level | `mod` declarations resolve to sibling files |
| Go | best-effort, file-level | imports under the module path resolve to internal packages |
| Java | manifest-only, repo-level | no module-level graph; import names do not map to artifacts reliably |

A consumer that needs a guarantee should treat best-effort edges as evidence, not proof,
the same way the repo-level graph already grades its edges by confidence.

## Symbol graph

The symbol graph (`index internals-symbols`, and the per-symbol pages inside `index wiki`)
extends the module graph down to functions, classes, and methods. It answers
GO-TO-DEFINITION (where a symbol is defined) and FIND-REFERENCES (who calls it), derived
from the Python AST, never inferred by a model, and byte-identical across runs.

A `SymbolDefinition` has an `id` of `module_id::name` (or `module_id::Class::method`), a
`kind` (`function`, `async_function`, `class`, `method`, `async_method`), and a `file:line`.
A `SymbolCall` carries the caller id, the resolved target id (or `null`), the bare name at
the call site, `file:line` evidence, and an honest `resolution`/`confidence` pair:

| Resolution | Confidence | Meaning |
|------------|------------|---------|
| `exact` | `high` | the call binds to a definition in the same module (or `self.m()` to a sibling method), read from the AST |
| `cross_module` | `moderate` | the callee is a `from <internal-module> import name` binding that names a real definition in this repo |
| `cross_module_unresolved` | `low` | the static scan could not bind the name (undefined name, attribute on an object whose type is unknown, or an import that names no definition); surfaced as an unresolved reference, never a guessed edge |

Dynamic dispatch (`getattr`, a variable holding a function) and files that fail to parse are
recorded in the symbol coverage object, not guessed at. Only Python is symbol-exact; other
languages keep their module-level graph and carry no symbol extraction.

Per-symbol wiki pages are sealed with the same per-page hash as every other page, and
`index wiki --verify` re-derives the symbol graph from the current tree: a resolved call a
page claims that the real graph does not contain is DRIFT (rule `symbol-call-not-in-graph`),
exactly as a forged module edge is. An unresolved reference is never a claimed edge, so it
never causes a false DRIFT. Above a symbol-count threshold the wiki omits the per-symbol
pages to avoid bloat; the symbol graph itself is still derivable and sealable on the CLI.
