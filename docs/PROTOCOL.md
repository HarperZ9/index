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

### How to verify a certificate

You do not trust a certificate. You re-run it.

1. Run the `recheck` command in the same workspace.
2. Recompute `content_sha256` and `criterion_sha256` from the fresh result with the
   canonical hash above.
3. Confirm the `verdict` matches.

If the hashes and the verdict agree, the certificate held. If they do not, the structure
or the criterion changed, which is itself the signal.

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
