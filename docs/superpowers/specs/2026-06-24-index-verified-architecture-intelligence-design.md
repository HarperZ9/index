# Design: Index 2.0 -- Verified Architecture Intelligence

> Date: 2026-06-24
> Status: Brainstormed and scoped. Spec recorded; plan next.
> Repo: PUBLIC `index` (`HarperZ9/index`, PyPI `index-graph`). Branch `feat/verified-architecture-intelligence` off `main` @ v1.2.0 (`6c8e685`).

## Summary

Index today is an excellent static cartographer. It scans a workspace, infers a repo-to-repo dependency graph from evidence, and renders it as JSON, an interactive dashboard, and a two-layer code-and-docs atlas. It answers "what does this workspace look like right now."

It does not yet answer the three questions that matter most once a codebase is alive:

1. What does it look like **inside** a repo, where architecture erosion actually happens.
2. Is its real structure **allowed**, measured against a rule a human declared.
3. Has it **drifted** since the last time we looked.

Index 2.0 adds those three answers and binds them to a verdict you can re-run. The spine is one continuous story: **look inside, declare the rule, check it, watch for drift, and hand back a certificate that re-checks from its own evidence.** The verdict is one of three words, MATCH, DRIFT, or UNVERIFIABLE, and never a fourth. There is deliberately no TRUSTED. You believe the certificate by re-running it, not because it told you to.

This is the reconcile loop, the project's core primitive, expressed natively in Index's domain. It is also what makes Index a flagship that stands alone and composes through a clean seam: the certificate and the pack are a generic, versioned, self-verifying contract that any consumer can hold, whether that is a CI gate, a human reviewer, or an external accountable agent.

## Goals

- See inside a repo: a module and file level dependency graph, not only repo as atom.
- Let a developer declare an architecture criterion in `.index.toml`: ordered layers, forbidden edges, a cycle ceiling, ownership and boundary rules.
- Check the real graph against that criterion and report every violation with evidence down to the file and line.
- Snapshot the graph deterministically and diff two snapshots into a drift report.
- Emit a certificate for `check` and `drift`: content hash, criterion hash, a MATCH / DRIFT / UNVERIFIABLE verdict, the findings, and the exact command to re-check.
- Specify and version the output as a documented protocol seam that external consumers can depend on.

## Non-goals (honest scope)

- Not a semantic compiler. Module-level resolution is import-evidence based, the same conservative discipline the repo-level resolvers already use. It locates and grades; it does not type-check.
- Not a refactoring tool. It reports cycles and violations; it does not rewrite code.
- Not cross-marketing. The peer interop lives entirely in the protocol seam. Index's README, USAGE, and CLI say nothing about sibling products. The contract is the schema, the hashes, and the verdict.
- No new runtime dependencies. Pure Python 3.11+ stdlib, the same as every existing subsystem.

## Global constraints (carried from the existing house style)

- **Zero runtime dependencies.** Standard library only.
- **Deterministic.** Same workspace and same criterion produce a byte-identical pack and an identical certificate. All collections sorted; hashing is over a canonical serialization.
- **Backward compatible.** Every new capability is additive. `map`, `graph`, `context`, `viz`, and `atlas` and their JSON are unchanged. The 217 existing tests stay green.
- **Local-first and self-contained.** No network, no accounts, no external URLs in any rendered artifact.
- **Evidence-carrying.** Every internal edge and every violation names the file and, where cheap, the line that witnessed it. Nothing is asserted without a citation, mirroring the existing `Signal` discipline.

## The capability, piece by piece

### 1. Module-level graph: `internals`

The repo-level resolvers already capture the raw import signal (`RawEdge` records the target name, the evidence file, and the line). Today that signal is normalized to repo-to-repo edges and the within-repo structure is collapsed. `internals` keeps it.

- A module node is a source unit within a repo: a Python module, a JS/TS file, a Rust module, a Go file or package, addressed by repo-relative path.
- An internal edge is an import from one module to another in the same repo, graded by the same evidence discipline.
- Outputs: internal cycles (reusing the existing Tarjan SCC over the internal edge set), layering depth, and per-module fan-in and fan-out so hub and god-modules surface.
- Language reach for module granularity at 2.0: Python (AST, exact), and best-effort file-level for JS/TS, Rust, and Go from the import scans already present. Java stays manifest-only and therefore repo-level only; this is stated, not hidden.

CLI: `index internals --root REPO [--json] [--cycles]`. Repo-level commands are untouched.

### 2. Architecture criteria: `[architecture]` in `.index.toml`

A new optional config block declares the rule the graph will be measured against. A criterion the model did not author.

```toml
[architecture]
# ordered layers, lowest first; an edge from a lower layer to a higher one is a violation
layers = ["core", "domain", "service", "web"]
# explicit forbidden edges, by repo or module glob
forbid = [
  { from = "core/**", to = "web/**" },
]
# the maximum number of dependency cycles tolerated (default: unset = not checked)
max_cycles = 0
# ownership / boundary assertions (optional)
[architecture.owns]
"payments/**" = "team-payments"
```

Parsing is pure and additive to `config.py`. Absence of the block means `check` reports UNVERIFIABLE for layer or forbid rules that were never declared, rather than inventing a pass.

### 3. The check: `check`

`check` evaluates a graph, repo-level by default and module-level under `--internals`, against the declared criteria.

- Each finding records the rule it broke, the offending edge, and the evidence file and line.
- Layer violations, forbidden edges, and cycle-ceiling breaches are all findings.
- The command exits non-zero when findings exist, so it works as a CI gate.

CLI: `index check --root ROOT [--internals] [--json]`.

### 4. Snapshots and drift: `snapshot`, `drift`

- `snapshot` writes a canonical, deterministic snapshot of the graph (and, with `--internals`, the module graph) to a file. The format is sorted and stable so two runs are byte-identical.
- `drift` diffs two snapshots: repos and modules added or removed, edges added or removed, cycles introduced or cleared, role changes, and any newly introduced criterion violations.

CLI: `index snapshot --root ROOT --out FILE` and `index drift --from OLD --to NEW [--json]`.

### 5. The certificate: the reconcile binding

`check` and `drift` emit a certificate, the heart of the verification story.

```json
{
  "schema": "index.certificate/1",
  "tool_version": "2.0.0",
  "kind": "check",
  "content_sha256": "<hash of the canonical graph or snapshot pair>",
  "criterion_sha256": "<hash of the declared criterion, or null>",
  "verdict": "MATCH | DRIFT | UNVERIFIABLE",
  "findings": [ { "rule": "...", "edge": "...", "evidence": "file:line" } ],
  "recheck": "index check --root . --internals --json"
}
```

- **MATCH**: the artifact satisfies the criterion.
- **DRIFT**: it does not, and every breach is itemized with evidence.
- **UNVERIFIABLE**: the criterion cannot be evaluated against this artifact (a layer names a repo that does not exist; no criterion was declared; a language whose module graph Index cannot resolve was asked for module-level layering). UNVERIFIABLE stops and says so. It never returns a guess wearing the costume of an answer.

The certificate re-checks from its own evidence: a consumer re-runs `recheck`, recomputes `content_sha256` and `criterion_sha256`, and confirms the verdict independently. The existing `viz/manifest.py` SHA-256 discipline is the precedent; this generalizes it from render integrity to verdict integrity.

### 6. The protocol seam

The pack and the certificate are specified in a new `docs/PROTOCOL.md` and versioned by their `schema` field. The document describes the shapes, the hashing rule, and the three verdicts in consumer-agnostic terms. It names no sibling product. Index's amplification of the wider system is exactly this: a stable, self-verifying artifact anyone can consume by re-running it. The interop is structural.

## Architecture and new units

New subsystems under `src/index_graph/`, each independently testable, each composing the existing primitives rather than editing them in place:

- `internals/` -- module discovery and the intra-repo graph (reuses `graph/cycles.py` over the internal edge set).
- `arch/` -- `criteria.py` (parse `[architecture]`) and `check.py` (evaluate, produce findings).
- `drift/` -- `snapshot.py` (canonical serialize and load) and `diff.py` (two-snapshot diff).
- `certify/` -- `certificate.py` (build and serialize the verdict certificate; the canonical hashing helper).
- `config.py` -- extended to parse the `[architecture]` block (additive, optional).
- `cli.py` -- new subcommands `internals`, `check`, `snapshot`, `drift`. Existing subcommands untouched.
- `docs/PROTOCOL.md` -- the seam specification.

The exact module boundaries are fixed in the implementation plan. The existing `viz` output stays byte-identical and its determinism tests stay green.

## Phasing (one plan, in order; each phase ends green and reviewable)

1. **Module graph foundation** -- `internals/` module discovery and the intra-repo edge build for Python (AST). Internal cycles and fan-in/out. Tests.
2. **Module graph reach** -- best-effort file-level edges for JS/TS, Rust, Go from the existing import scans. Honest per-language bounds. Tests.
3. **Criteria** -- parse `[architecture]` (layers, forbid, max_cycles, ownership) in `config.py`. Tests including malformed config.
4. **Check** -- evaluate repo-level and module-level graphs against criteria; findings with evidence; non-zero exit. Tests including the UNVERIFIABLE paths.
5. **Snapshot and drift** -- canonical snapshot; two-snapshot diff; the drift report. Determinism tests.
6. **Certificate** -- the verdict certificate for `check` and `drift`; canonical hashing; the re-check round-trip proven in a test (re-run reproduces the verdict and the hashes).
7. **CLI and protocol** -- wire the four subcommands; write `docs/PROTOCOL.md`; README and USAGE sections; CHANGELOG; version bump.
8. **Release prep** -- full suite green; dogfood over `c:/dev`; tag-ready. The PyPI publish itself waits for explicit human go (no auto-deploy).

Stretch, only if the spine lands clean and time allows, explicitly optional and not part of the committed scope: a TypeScript-proper resolver (tsconfig paths) or a C/C++ resolver (`#include` plus CMake), and promoting external dependencies to first-class graph nodes.

## Error handling and honest bounds

- **Module resolution quality varies by language.** Python is AST-exact. JS/TS, Rust, and Go are regex and best-effort at file granularity, the same conservative discipline as the repo-level resolvers; dynamic and conditional imports may be missed. Java is manifest-only and stays repo-level. Each bound is stated in `PROTOCOL.md` and in `--help`, not hidden.
- **UNVERIFIABLE is a first-class outcome, not a failure mode.** When a criterion cannot be evaluated, the certificate says UNVERIFIABLE and names why. This is correctness over the appearance of completeness.
- **Determinism under growth.** Module-level graphs are larger; all collections are sorted and the snapshot is canonical, so hashing and diffs stay stable. A determinism test guards each new pack.
- **Scale.** Very large repos produce large module graphs. `internals` honors the existing prune configuration and is opt-in per command, so the default repo-level path keeps its current performance.
- **No criterion present.** `check` and `drift` still run and report structure; the verdict for undeclared rules is UNVERIFIABLE, never a fabricated MATCH.

## Success criteria

1. `index internals --root <repo> --json` emits a deterministic module-level dependency graph with internal cycles and per-module fan-in and fan-out, AST-exact for Python and best-effort for JS/TS, Rust, and Go.
2. A `[architecture]` block in `.index.toml` is parsed; `index check` reports layer violations, forbidden edges, and cycle-ceiling breaches, each with evidence to the file and line, and exits non-zero when findings exist.
3. `index snapshot` writes a byte-stable snapshot; `index drift --from A --to B` reports added and removed nodes and edges, introduced and cleared cycles, role changes, and newly introduced violations.
4. `check` and `drift` emit a certificate with a MATCH / DRIFT / UNVERIFIABLE verdict; a test proves the re-check round-trip reproduces the verdict and both hashes independently.
5. `docs/PROTOCOL.md` specifies the pack and certificate shapes, the hashing rule, and the three verdicts, in consumer-agnostic terms naming no sibling product.
6. The 217 existing tests stay green; the new subsystems add their own tests; all new packs and certificates are deterministic.
7. Every new capability is additive; the five existing subcommands and their JSON are unchanged; zero new runtime dependencies.
8. The branch is tag-ready for 2.0.0. The actual PyPI release waits for explicit human approval.
