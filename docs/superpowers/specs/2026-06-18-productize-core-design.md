# Productize the Core -- Design Spec

- **Date:** 2026-06-18
- **Status:** Approved (design); pending implementation plan
- **Target version:** 0.2.0
- **Scope:** Track A of the productization roadmap -- make `workspace-repo-map`
  a tool installable and usable by people other than its author.

---

## 1. Context & motivation

`workspace-repo-map` v0.1.0 is a single 268-line module (`src/workspace_repo_map/map.py`)
that scans a workspace root for git repositories and emits a compact, privacy-sanitized
JSON inventory. It is well-built but shaped around one private workspace. Four things
block it from being a general tool:

1. **Hardcoded personal taxonomy.** `ROOT_CLASSES`, `ROOT_BOOTSTRAP_FILES`, and
   `repo_class`/`root_class` (`map.py:41-60, 178-214`) encode one operator's lane
   conventions. Commit `0a2e182` began scrubbing these for public release; this work
   finishes it. A related operator-specific hardcode -- the `scratch/venvs` prune
   special-case (`_skip_generated_tree`, `map.py:241-247`) -- is removed as well; pruning
   becomes the universal safety set plus `[scan] prune` config only.
2. **Two competing CLIs.** `map.py:build_parser` and `cli.py:build_parser` both exist;
   the entry point reconstructs an argv list and re-dispatches (`cli.py:16-19`), with a
   dead assignment at `cli.py:18` and divergent defaults.
3. **No defined public API.** `__init__.py` is `from .map import *` with no `__all__`,
   leaking stdlib imports; there is no `__version__` and the output JSON has no
   `schema_version`.
4. **Serial git fan-out.** `repo_row` makes ~4–5 `git` subprocess calls per repo
   (`map.py:155-175`), all repos processed serially -- the dominant cost at workspace scale.

"Productize the core" addresses all four in one refactor.

## 2. Goals / Non-goals

**Goals**
- Classification is data-driven via an optional `.repomap.toml`; with no config, behavior
  is generic and non-personal.
- One CLI, one argument parser.
- A stable, explicit public API (`__all__`, `__version__`) and a versioned output schema
  (`schema_version: 1`).
- Per-repo git calls run in parallel, output remains deterministic.
- Output portability is configurable -- shareable/sanitized by default, opt-in local mode.
- Zero runtime dependencies preserved.

**Non-goals (YAGNI for this spec)**
- Markdown / compact / token-budgeted emit modes (Track B).
- Snapshot history, map diffing, upstream ahead/behind, shape deltas (Track C).
- Rule predicates beyond path globs (no remote/marker matching in user rules yet).
- Global/XDG config, plugin system.

The module seams below are placed so Tracks B and C attach without rework.

## 3. Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| Default classification (no config) | **Neutral** -- generic fallback ladder; personal taxonomy ships as example config | Required for "installable by others"; finishes the `0a2e182` scrub |
| Rule model | **Ordered path-glob rules, first match wins**, then a built-in remote-host fallback | Familiar `.gitignore`/CODEOWNERS semantics; covers lane layouts directly |
| Output schema | **Deliberate `schema_version: 1`, free to restructure** | Nothing pins the schema yet; cheapest moment to set a clean v1 |
| Refactor scope | **Modular split** of `map.py` into focused units | Right-sized isolation; respects file/function size gates; hosts later tracks |
| TOML parsing | **stdlib `tomllib`** → Python floor raised to **3.11** | Keeps `dependencies = []`; aligns README (already claims 3.11+) with pyproject |
| Output portability | **Config switch `[output] portable`, default `true`**; no CLI flag | Serves shareable and private-local maps from one tool, with no safe-default foot-gun |

## 4. Architecture

### 4.1 Modules

| Module | Owns | Depends on |
|---|---|---|
| `model.py` | `RepoRow`, `Map` dataclasses, `SCHEMA_VERSION = 1`, `to_json`. Pure data -- no I/O, git, or config. | stdlib |
| `config.py` | `Rule`, `Config`, `load_config()`, `default_config()`, neutral defaults, prune/marker lists, TOML parse + validation, glob→regex translation. | `tomllib`, `re` |
| `classify.py` | `classify(rel_path, remote, config) -> str`: ordered glob match → remote-host fallback → default. Pure; used for repos and root entries. | `config` |
| `gitmeta.py` | `run_git()`, `repo_metadata()` (status counts, branch, head, sanitized origin). Subprocess + redaction layer. | `subprocess`, `re` |
| `scan.py` | Orchestration: `discover_repos()` (os.walk + prune), parallel fan-out, apply classify, assemble `Map`, `write_map()`. | `gitmeta`, `classify`, `config`, `model` |
| `cli.py` | Single argparse parser + `main()`. The one entry point. | `scan`, `config`, `model` |
| `__init__.py` | Public API via explicit `__all__` + `__version__`. | -- |
| `__main__.py` | `from .cli import main`. | `cli` |

Isolation win: `gitmeta` (subprocess) and `config` (parsing) never touch each other, and
`classify` is a pure function. The parts previously untestable in isolation -- discovery,
classification, redaction -- each get real unit tests.

### 4.2 Data flow

```
cli.main(argv)
 └─ load_config(--config | <root>/.repomap.toml | built-in defaults)
 └─ scan.build_map(root, config)
      ├─ discover_repos(root, config)          # os.walk + prune (single-threaded)
      ├─ ThreadPoolExecutor → repo_metadata()  # git calls fan out, one task per repo
      ├─ classify(rel, remote, config)         # ordered rules → remote fallback
      └─ assemble Map{schema_version, counts, top_level, repositories}
 └─ emit: write JSON to --output   |   print to stdout (--json)
```

### 4.3 Concurrency

`ThreadPoolExecutor` (threads -- the work is git-subprocess/IO-bound). Each task runs one
repo's git calls; the pool replaces the serial loop. Discovery stays single-threaded
(`os.walk`). **Determinism is preserved** by sorting results by path *after* the pool
drains -- never relying on completion order. Worker count via `--jobs`, default
`min(32, (os.cpu_count() or 4) * 5)`.

## 5. Config system

### 5.1 `.repomap.toml` schema

All sections optional; an absent file means pure neutral behavior.

```toml
# Ordered classification rules -- first match wins.
# `pattern` matches each repo's workspace-relative POSIX path.
[[rule]]
pattern = "public/**"
class   = "public"

[[rule]]
pattern = "protected/**"
class   = "protected"

# Scan tuning (optional)
[scan]
jobs    = 16                      # default min(32, cpu*5)
prune   = ["vendor", "target"]    # ADDED to the built-in safety set; never replaces it
markers = ["go.mod", "Gemfile"]   # REPLACES the default marker list when present

# Privacy (optional)
[privacy]
omit_origin_classes = ["protected"]   # origins for these classes are dropped entirely

# Output (optional)
[output]
portable    = true   # default; false = absolute paths + root, for private local maps
annotations = { }    # arbitrary passthrough key/values, emitted verbatim when non-empty
```

### 5.2 Glob semantics

Implemented as a small glob→regex translator in `config.py` (stdlib `re`); `fnmatch`
ignores `/`, and portable `**` in `PurePath.match` only arrived in 3.13. Each rule's
pattern compiles to a regex once at config load, not per repo.

- `*` -- matches within a single path segment (stops at `/`)
- `**` -- matches zero or more segments; `public/**` matches `public`, `public/demo`,
  and `public/demo/sub`
- literal segments match exactly
- first matching rule in file order wins

The **same evaluator classifies top-level entries** (today's `root_class`); the entry
name is the path, so `pattern = "secrets"` classifies a root `secrets/` directory.

### 5.3 Fallback ladder (the neutral default)

When no rule matches a repo:

1. no origin remote → `"local"`
2. origin host ∈ public-hosting set (`github.com`, `gitlab.com`, `bitbucket.org`,
   `codeberg.org`, `git.sr.ht`) → `"public"`
3. otherwise (self-hosted / unknown host) → `"private"`

Non-repo root entries with no rule match fall back to `"hidden"` (dotfiles) or `"entry"`.
Rule matching is identical for repos and root entries; only the no-match fallback differs
by kind (the ladder above for repos, `"hidden"`/`"entry"` for root entries). `classify`
therefore takes the entry kind alongside the path and optional remote.

> `"public"` here means *"origin is on a public code-hosting platform"* -- a heuristic,
> **not** a guarantee of repository visibility. Documented as such in the README.

### 5.4 Discovery & precedence

`--config PATH` (error if missing) → else `<root>/.repomap.toml` → else built-in neutral
defaults. No global/XDG config in v1.

### 5.5 Validation

`load_config` fails fast with actionable messages:

- TOML parse errors report file + line.
- A rule missing `pattern`/`class` names the offending index.
- Invalid globs and non-positive `jobs` error out.
- Unknown keys warn to stderr but continue (forward-compat).
- An empty rule list is valid (all repos use the fallback ladder).

### 5.6 Privacy generalization

This is how the personal `protected` policy stops being hardcoded:

- **Credential/userinfo redaction** in origin URLs (`token@…`, `?token=…`) stays
  **always-on** for every repo -- a security invariant, preserving today's
  `sanitize_origin` regexes (`map.py:61-64, 109-113`).
- **Full origin omission** now keys off `[privacy].omit_origin_classes`, default **empty**
  in the shipped neutral config. The operator's taxonomy moves into a shipped
  `example.repomap.toml` that sets `omit_origin_classes = ["protected"]`, reproducing
  today's behavior as *their* config rather than everyone's default.

**Pipeline ordering** (must be explicit so the fallback ladder keeps working): credential
redaction (host-preserving) happens in `gitmeta`; `classify` reads the redacted origin's
host for the fallback ladder; full origin omission is applied last, in `scan` during output
assembly, once the class is known. Omission must not happen in `gitmeta`, or §5.3 step 2
could never match a host.

### 5.7 `Config` shape

```python
@dataclass(frozen=True)
class Rule:
    pattern: str
    class_: str

@dataclass(frozen=True)
class Config:
    rules: tuple[Rule, ...]
    extra_prune: frozenset[str]
    markers: tuple[str, ...]
    jobs: int
    omit_origin_classes: frozenset[str]
    portable: bool
    annotations: dict[str, Any]
```

`load_config(path: Path | None, root: Path) -> Config`; `default_config() -> Config`.
Neutral defaults live in `config.py` as the single source.

### 5.8 Portable vs local mode

`workspace-repo-map` serves two audiences: maps meant to be **shared** (issues, agent
prompts, docs) and maps kept **private** for local navigation. One config switch covers
both, and **portable is the default**.

`[output] portable` (bool, default `true`):

- **`true` (portable):** repository `path`s are workspace-relative POSIX; the real root is
  represented only by `root_sha256_prefix`; `absolute_paths_included` is `false`. The
  shareable default.
- **`false` (local):** repository `path`s and an added top-level `root` are emitted
  **absolute**; `absolute_paths_included` is `true`. For private, machine-local maps that
  are never shared.

Two invariants hold in **both** modes:

- **Credential/userinfo redaction is always on** (security; §5.6). It fires only on
  credential-shaped URLs, so it is a no-op for clean origins.
- **`omit_origin_classes` is orthogonal to `portable`** -- origin omission is a class-keyed
  privacy choice applied regardless of mode.

`[output] annotations` (table, default empty): arbitrary operator-supplied key/values
emitted verbatim under a top-level `annotations` object, and only when non-empty. A
passthrough for local context (e.g. an operating-model descriptor or a policy block)
without the tool hardcoding any of it.

There is **no CLI flag** for portability in v1 -- non-portable output requires a deliberate
`[output] portable = false` in a config file, preserving the safe-by-default identity. The
library API carries it on `Config`: `build_map(root, config)` honors `config.portable`, and
programmatic callers select local mode via `Config(portable=False, ...)`.

## 6. Output schema v1

```json
{
  "schema_version": 1,
  "tool_version": "0.2.0",
  "generated_at": "2026-06-18T12:34:56-07:00",
  "root_sha256_prefix": "abcd1234ef567890",
  "absolute_paths_included": false,
  "repo_count": 6,
  "dirty_count": 4,
  "class_counts": { "public": 3, "private": 2, "local": 1 },
  "top_level": [
    { "name": "public", "kind": "directory", "class": "public", "bytes": null, "modified": "..." }
  ],
  "repositories": [
    { "path": "public/demo", "class": "public", "branch": "main", "head": "abc1234",
      "origin": "https://github.com/owner/repo.git",
      "dirty_count": 0, "untracked_count": 1, "markers": ["README.md", "pyproject.toml"] }
  ]
}
```

Deltas from v0.1.0 output:

- **Added:** `schema_version`, `tool_version`, `class_counts`.
- **Removed:** the duplicated `relative` field; the protected-specific split
  (`normal_repo_count`, `protected_repo_count`, `normal_dirty_count`,
  `protected_dirty_count`, `protected_policy`); the constant `root: "<local-root>"`.
  These are replaced by generic `repo_count` / `dirty_count` / `class_counts`.
- **Kept:** `root_sha256_prefix`, `absolute_paths_included` (also seed Track C correlation),
  `generated_at`, `top_level`.
- **Mode-dependent (§5.8):** `absolute_paths_included` reflects `[output] portable`; local
  mode (`portable = false`) additionally emits an absolute top-level `root` and absolute
  repository `path`s. An optional `annotations` object appears when configured.

`model.py` dataclasses (`to_json` maps `class_` → `class`):

```python
SCHEMA_VERSION = 1

@dataclass(frozen=True)
class RepoRow:
    path: str
    class_: str
    branch: str
    head: str
    origin: str
    dirty_count: int
    untracked_count: int
    markers: tuple[str, ...]

@dataclass(frozen=True)
class Map:
    schema_version: int
    tool_version: str
    generated_at: str
    root_sha256_prefix: str
    root: str | None              # absolute root in local mode; None when portable
    absolute_paths_included: bool
    repo_count: int
    dirty_count: int
    class_counts: dict[str, int]
    top_level: list[dict]
    repositories: tuple[RepoRow, ...]
    annotations: dict[str, Any]   # emitted only when non-empty
```

## 7. CLI surface

```
workspace-repo-map [--root PATH] [--output PATH] [--json] [--config PATH] [--jobs N] [--version]
```

- `--root` default cwd; `--output` default `<root>/WORKSPACE-REPO-MAP.json`.
- `--json` prints to stdout instead of writing.
- `--config` explicit config path; `--jobs` worker override; `--version` prints tool
  version and exits 0.
- Exit 0 on success; non-zero on config error / unreadable root.
- Portability is **config-driven** (`[output] portable`); there is intentionally no CLI
  flag for it in v1 (§5.8).
- Entry point unchanged: `workspace_repo_map.cli:main`.

## 8. Public API

`__init__.py` replaces `from .map import *`:

```python
from .model import Map, RepoRow, SCHEMA_VERSION
from .config import Config, Rule, load_config, default_config
from .classify import classify
from .scan import build_map, write_map, discover_repos

__version__ = "0.2.0"
__all__ = [
    "build_map", "write_map", "discover_repos",
    "Map", "RepoRow", "SCHEMA_VERSION",
    "Config", "Rule", "load_config", "default_config",
    "classify", "__version__",
]
```

`__version__` is single-sourced here; `pyproject.toml` switches to hatchling **dynamic
version** reading it, eliminating drift between pyproject, the README badge, and the output
`tool_version` (which reads `__version__`).

`build_map(root, config)` honors `config.portable` and `config.annotations`; programmatic
callers select local mode by constructing `Config(portable=False, ...)`.

## 9. Error handling

Honors "never swallow errors silently":

- `run_git` keeps `timeout=20`, `check=False`, empty-string fallback.
- A repo whose git calls fail still appears as a *degraded* row
  (`branch`/`head` = `"unknown"`), but a pool-task exception is **caught and logged to
  stderr with the repo path** -- never silently dropped.
- Config errors are **fatal / fail-fast** (user input, not environmental).
- An unreadable `--root` produces a clear error and non-zero exit.

## 10. Testing plan

Expand from 4 tests to per-module suites with meaningful assertions, covering the
previously-untested discovery/classification/concurrency core:

- `test_config` -- TOML parse, validation errors, defaults, prune-extend vs marker-replace,
  discovery precedence.
- `test_classify` -- `*` vs `**` segment semantics, first-match-wins ordering, the fallback
  ladder (local/public/private), root-entry fallback.
- `test_gitmeta` -- `sanitize_origin` (+ always-on credential redaction), omission via
  `omit_origin_classes`, git-failure → degraded row.
- `test_scan` -- discovery/pruning incl. nested repos, **parallel-build determinism**
  (sorted output), absolute-path omission (migrated from today's test), `class_counts`.
- `test_model` -- `to_json` key mapping, `schema_version` present, no `relative` field.
- `test_cli` -- arg parsing, `--json` vs `--output`, `--version`, missing `--config` →
  error exit.
- `test_output_mode` -- portable vs local emission (relative paths + `root_sha256_prefix`
  vs absolute `path`s + absolute `root`), `absolute_paths_included` correctness, and
  `annotations` passthrough emitted only when set.

## 11. Migration

Ship `example.repomap.toml` reproducing today's behavior (lane rules +
`omit_origin_classes = ["protected"]`). The operator copies it to their workspace root as
`.repomap.toml`; generated maps render as before, with the personal taxonomy now in their
config rather than the shipped binary. README + CHANGELOG document the move.

## 12. Versioning & docs

- Version 0.1.0 → **0.2.0** (new features plus a breaking output change under a fresh
  `schema_version`; pre-1.0, so a minor bump).
- Update README badges (version + Python 3.11) and the install/usage notes.
- CHANGELOG 0.2.0 entry covering config-driven classification, the CLI unification, the
  public API + schema, parallel scanning, and the Python floor change.

## 13. Open questions

None outstanding. All load-bearing forks (default behavior, rule model, schema freedom,
refactor scope, TOML/Python floor) are resolved above.
