# Design: Repo-level dependency graph + context engine

> Date: 2026-06-23
> Status: Approved (brainstorming), pending implementation plan
> Package: `workspace-repo-map` (this repo)
> Branch: `feat/repo-graph-context-engine`

## Summary

`workspace-repo-map` today is a *sensor*: it discovers a workspace's git topology
(remotes, branches, dirty counts, marker files, classification) and writes a compact
JSON map. It does not infer how the repositories relate to each other.

This design adds the differentiated half — an **inference engine** that derives a
**repo-level dependency graph from real code** (manifests + source imports), assigns
each repo a **structural role derived from topology** (not a hand-authored ontology),
and renders the result as a **synthesis context pack** (relations + roles + prose) in
the representation a prior experiment validated as best for model synthesis of a large
codebase's shape.

The engine ships *inside* this package as two new, internally isolated module groups
(`graph/`, `context/`) and two new CLI subcommands (`graph`, `context`). The existing
single-command behavior is preserved. Zero new runtime dependencies.

## Why this, why now

The articulated niche — *productizing / dependency-mapping sprawling multi-repo
codebases, and keeping their architecture from quietly eroding under AI-agent-driven
development* — is a generic pain. The sensor is already generic and product-grade. The
context engine that fills the niche currently exists only as a bespoke internal tool
(`project-docs/tools/context_pack.py`) whose edges and roles come from a **hand-authored
organ registry**, not from code. It cannot run on an arbitrary codebase.

This design closes that gap: derive the structure automatically, generically, while
preserving two guarantees the internal tool established —

1. **No editorializing.** Every emitted line traces to a data field or an evidence
   record. The engine never synthesizes interpretive conclusions ("X is the keystone").
2. **Salience faithfulness.** Decorative prominence (markers) must not outshine
   structural centrality (hubs); the pack audits and flags mismatches.

To these it adds a third guarantee that is the heart of the engineering caliber:

3. **Evidence-carrying inference (proof before trust).** The engine never asserts a
   dependency. It reports the dependency *and its witnesses* — the manifest entry and/or
   source import that justify the edge, with file (and line where cheap) and a confidence
   grade. An edge with no evidence cannot exist.

## Scope

### In scope (v1)

- Repo-level dependency inference (which repo depends on which) for **Python** and
  **JavaScript/TypeScript**.
- Two edge signals per ecosystem: **declared** (manifest) and **observed** (source import).
- A pluggable **resolver** interface so additional ecosystems are added without touching
  the engine.
- Derived **structural roles** (archetypes) from the resulting topology.
- A **context pack** renderer (text + JSON) carrying relations + roles + prose, with the
  no-editorializing and salience-faithfulness guarantees ported from `context_pack.py`,
  plus `--focus <repo>` bidirectional closure.
- Two new CLI subcommands (`graph`, `context`); `map` preserved as the default.
- A **dogfood acceptance test**: run over the author's corpus and measure how much of the
  hand-authored organ-registry edge set the inference recovers.

### Out of scope (deferred to the next epic)

- Module-level (intra-repo) dependency graph.
- Architecture-drift detection (cycles, layer violations, role changes over time).
- Third-party dependency nodes (external deps are recorded on edges but not graphed as nodes).
- Resolvers beyond Python and JS/TS (C++, Lua, Rust, Go, QuantaLang).
- The vision / rendered-shape arm (perceive the graph image).
- Rewiring the internal `context_pack.py` to consume this tool's output (a follow-up,
  not part of v1).

## Architecture

New modules are additive and self-contained. The sensor (`scan.py`, `classify.py`,
`gitmeta.py`, `config.py`, `model.py`) is unchanged.

```
src/workspace_repo_map/
  cli.py              # gains subcommands: map (default), graph, context
  graph/
    __init__.py
    resolvers/
      __init__.py
      base.py         # Resolver protocol + RawEdge dataclass — the generic seam
      python.py       # pyproject.toml / requirements*.txt / setup.cfg|py + .py import scan
      javascript.py   # package.json + .js/.ts/.jsx/.tsx import|require scan
    edges.py          # RawEdge -> resolved repo->repo Edge, with evidence + confidence
    roles.py          # derive structural archetypes from topology
    build.py          # repo inventory + working trees -> DependencyGraph
  context/
    __init__.py
    pack.py           # relations + roles + prose -> text/JSON; salience audit; --focus closure
```

**Data flow.**

```
workspace-repo-map map   (existing)         -> WORKSPACE-REPO-MAP.json (repo inventory)
                                               |
graph.build.build_graph(inventory, root)  <---+  reads repo paths from the map (or scans --root)
   for each repo: each matching Resolver yields exposed_names + raw_edges(evidence)
   global index: exposed_name -> repo
   resolve each RawEdge target -> internal repo (Edge) or external (recorded, not a node)
   roles.derive(graph) -> structural archetype labels + degree evidence
   => DependencyGraph
                                               |
context.pack.render(graph)                 <---+  relations + roles + prose(README) -> text/JSON
```

### Dependencies

Zero new runtime dependencies. Python manifests via stdlib `tomllib` (3.11+, already the
floor). `package.json` via stdlib `json`. Imports via `ast` (Python) and a conservative
regex/tokenizer pass (JS/TS — no TS compiler dependency). `pytest` remains the only
(optional) test dependency.

## Component: the resolver seam (`graph/resolvers/base.py`)

The interface that makes the engine generic. One file per ecosystem implements it.

```python
@dataclass(frozen=True)
class RawEdge:
    target_name: str          # the name imported/declared (e.g. "requests", "@scope/pkg")
    signal: str               # "manifest" | "import"
    evidence_file: str        # repo-relative path of the witnessing file
    evidence_line: int | None # line number where cheap to capture, else None
    raw_spec: str             # the literal text witnessed (dep spec or import statement)

class Resolver(Protocol):
    name: str
    def matches(self, repo_root: Path) -> bool: ...
    def exposed_names(self, repo_root: Path) -> set[str]: ...
    def raw_edges(self, repo_root: Path) -> list[RawEdge]: ...
```

- `matches` — is this ecosystem present in the repo (manifest exists)?
- `exposed_names` — the import names / package names this repo *publishes* (its
  distribution name and top-level importable packages). Used to build the global index
  that turns a target name into an internal repo.
- `raw_edges` — every declared dependency (from the manifest) and every observed import
  (from source), each as a `RawEdge` carrying its witness.

A repo may match multiple resolvers (polyglot repos); all matches contribute.

### `graph/resolvers/python.py`

- `matches`: any of `pyproject.toml`, `setup.cfg`, `setup.py`, `requirements*.txt`.
- `exposed_names`: distribution name from `[project].name` (pyproject) / `setup.cfg`;
  top-level package/module names under the repo (top-level dirs with `__init__.py`, plus
  top-level single-file modules, plus a `src/` layout's first level). Normalized
  (lowercased, `-`/`_` unified) for matching.
- `raw_edges`:
  - manifest: `[project].dependencies` + `[project.optional-dependencies]` in pyproject;
    `install_requires`/`extras_require` in setup.cfg; each line of `requirements*.txt`.
    Target name is the parsed distribution name (strip version specifiers/markers).
  - import: parse each `.py` with `ast`; collect `import X` / `from X import …` top-level
    module names. `evidence_line` = the node's `lineno`.

### `graph/resolvers/javascript.py`

- `matches`: `package.json`.
- `exposed_names`: `name` field from `package.json` (including scope).
- `raw_edges`:
  - manifest: `dependencies` + `devDependencies` + `peerDependencies` keys.
  - import: conservative regex pass over `.js/.jsx/.ts/.tsx` for `import … from "X"`,
    `require("X")`, and dynamic `import("X")`. Bare specifiers only (a leading `.` or `/`
    is a relative path → intra-repo, ignored at repo granularity). `evidence_line` = the
    matched line number.

No TypeScript compiler is invoked; the regex pass is deliberately conservative and may
miss exotic forms. That is acceptable: missed imports lower an edge's confidence or omit
it; they never fabricate one. (See "Honest bounds.")

## Component: edge resolution (`graph/edges.py`)

```python
@dataclass(frozen=True)
class Edge:
    from_repo: str
    to_repo: str | None       # None when external (unresolved to an internal repo)
    target_name: str
    external: bool
    confidence: str           # "high" | "moderate" | "low"
    signals: tuple[Signal, ...]   # the evidence records (kind, file, line, raw_spec)
```

Algorithm:

1. Build `index: normalized_name -> repo` from every resolver's `exposed_names` across
   all repos. On collision (two repos expose the same name) record both and mark resolved
   edges to that name `low` confidence with an `ambiguous` note.
2. For each repo's `RawEdge`s, resolve `target_name` against the index:
   - resolves to a *different* internal repo → internal `Edge` (`external=False`).
   - resolves to the same repo → dropped (self-edge, not a relation).
   - no match → external `Edge` (`external=True`, `to_repo=None`); recorded for the
     "what third-party feeds repo X" view, not promoted to a graph node in v1.
3. Merge `RawEdge`s sharing `(from_repo, resolved_target)` into one `Edge`, unioning their
   signals.
4. Confidence grade:
   - `high`: both a `manifest` and an `import` signal present.
   - `moderate`: exactly one signal kind present.
   - `low`: target name is ambiguous (index collision) or a very short/common token
     (configurable stop-set, e.g. single-segment names ≤ 2 chars).

**Invariant (tested):** no `Edge` may exist with an empty `signals` tuple.

## Component: role inference (`graph/roles.py`)

Replaces the internal tool's hand-authored afferent/efferent/integrative anatomy with
archetypes derived purely from topology + repo facts. Each role carries its evidence
(degree counts and/or the marker file that justifies it). No domain ontology, no
editorializing. Roles are not mutually exclusive; a repo may carry several.

| Role           | Derivation (evidence)                                                    |
|----------------|--------------------------------------------------------------------------|
| `entrypoint`   | declares an executable entry: `[project.scripts]`/console_scripts, `bin` in package.json, or a top-level `__main__` |
| `library`      | is in `exposed_names` AND has internal in-degree ≥ 1, no entrypoint      |
| `hub`          | internal in-degree == max in-degree AND ≥ 2 (convergence point)          |
| `orchestrator` | internal out-degree == max out-degree AND ≥ 3 (symmetric with `hub`)     |
| `leaf`         | internal in-degree == 0 AND internal out-degree == 0 BUT matched a resolver (a real but unconnected project) |
| `isolated`     | matched no resolver / no manifest (the engine can say nothing structural about it) |

The `hub` derivation reuses the existing `structural_salience` definition so the role
layer and the salience audit agree by construction.

## Component: context pack (`context/pack.py`)

Ports the proven renderer from `context_pack.py`, adapted to *derived* inputs.

- **Roles section** — `repo: <roles> — <evidence>` (e.g. `core-lib: library, hub —
  in-degree 7`).
- **Relations section** — `A -> B: <signals summary> [confidence]`, external deps listed
  separately as `A -> (external) name`.
- **Inventory section** — per repo, prose **extracted** from the README's first paragraph
  or the manifest `description` field. Never authored. A repo with no README/description
  shows `(no description)`.
- **JSON sidecar** — `{roles, relations, salience, salience_audit, repos}`.
- **Guarantees ported verbatim in behavior:**
  - `structural_salience` (in/out degree + hub flag).
  - `salience_audit` (decorative-non-hub / unmarked-hub) — markers are now *derived*
    (e.g. `entrypoint`, `published`) rather than hand flagship tags.
  - **No-editorializing structural test** — a test asserts the renderer source contains
    no hardcoded interpretive sentences and every output line maps to a field/evidence.
  - `--focus <repo>` — bidirectional transitive closure (cycle-safe), text or JSON.

## CLI (`cli.py`)

Introduce subcommands while preserving backward compatibility.

```
workspace-repo-map [--root .] [--output …] [--json] [--config …] [--jobs N]   # default == `map`
workspace-repo-map map     …same flags as today…
workspace-repo-map graph   [--root .] [--map WORKSPACE-REPO-MAP.json] [--json]
workspace-repo-map context [--root .] [--map …] [--focus REPO] [--audit] [--json]
```

- **Backward compatibility:** if `argv[0]` is not a known subcommand (or no args), dispatch
  to `map`. Existing invocations (`workspace-repo-map --root . --json`) behave exactly as
  in v0.2.0.
- `graph` / `context` read repo paths from an existing map (`--map`) when given, else scan
  `--root` directly (reusing the sensor's discovery).
- Exit codes: `0` success; `2` for an unknown `--focus` target (with a near-match hint),
  mirroring the internal tool; `1` reserved for unexpected errors.

## Error handling (fail-closed, never fabricate)

- A repo whose manifest is malformed (unparseable `pyproject.toml`/`package.json`): record
  a parse warning for that repo, emit its node with whatever signals parsed, never crash
  the run and never invent edges.
- An unreadable source file: skip it with a warning; its imports are simply absent (lowers
  confidence, never fabricates).
- An import that resolves to no internal repo: external edge, not an error.
- An ambiguous name (index collision): `low` confidence + `ambiguous` note, both candidate
  repos recorded; never silently pick one.
- All warnings are collected and surfaced (count + list) rather than dropped — the run is
  honest about what it could not see.

## Testing strategy (TDD)

Synthetic fixture repos under `tests/fixtures/` (tiny, hand-built Python and JS/TS trees
with known manifests, imports, and expected edges).

1. **Resolver unit tests** — `python.py` / `javascript.py`: given a fixture repo, assert
   exact `exposed_names` and the `RawEdge` set (target, signal, evidence file/line).
2. **Edge resolution** — internal vs external classification; signal merge; confidence
   grading (high/moderate/low); ambiguity handling; the **no-empty-signals invariant**.
3. **Role derivation** — on a synthetic topology, assert hub/library/entrypoint/
   orchestrator/leaf/isolated assignments and their evidence.
4. **Ported guarantees** — no-editorializing structural test; salience audit (decorative-
   non-hub, unmarked-hub); `--focus` closure + cycle safety; CLI backward-compat (bare
   invocation still writes the map).
5. **Dogfood acceptance** (separate, opt-in, not in the default unit slice) — run `graph`
   over the author's `c:/dev` corpus and report the fraction of `organ_registry_data`'s
   hand-authored edges recovered by inference, plus false-positive edges for review. This
   is the validation metric for "derive structure from real code, not hand authoring."

Per repo conventions, the default test slice stays fast and synthetic; the corpus dogfood
is an explicit, separately-invoked acceptance run.

## Honest bounds

- **Conservative import scanning** (especially JS/TS regex, and Python dynamic
  `importlib`/`__import__`) means recall < 100%. By design the failure mode is *omission
  or lowered confidence*, never fabrication. The dogfood acceptance test quantifies recall
  against a known edge set.
- **Repo granularity only.** Two repos either relate or they don't; intra-repo module
  structure (where architecture erosion actually shows) is the deferred next epic.
- **Name-based resolution.** Internal edges rely on a repo's exposed name matching an
  import/dep name. Vendored copies, renamed forks, and path-only installs can miss; these
  surface as external edges (honest under-claim) rather than wrong internal edges.

## Success criteria

1. `workspace-repo-map graph --root <dir>` produces a JSON graph where **every edge
   carries ≥ 1 evidence record** and a confidence grade.
2. `workspace-repo-map context --root <dir>` produces a text + JSON pack with the three
   sections, passing the no-editorializing structural test and emitting a salience audit.
3. Existing v0.2.0 invocations behave identically (backward-compat test passes).
4. The full synthetic test slice passes and runs fast (< ~10 s).
5. The dogfood acceptance run reports a concrete recovery fraction against the
   hand-authored organ-registry edges (a number to improve against, not a pass/fail gate).
6. No new runtime dependencies; `pip install workspace-repo-map` still pulls nothing.
