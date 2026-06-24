# index atlas — Engine (Plan 1 of 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the atlas *engine* — discover the workspace's markdown as `doc` nodes and assemble a two-layer code+knowledge graph (repos + docs + the four edge types) — exposed as `index atlas --json`.

**Architecture:** A new pure-stdlib `knowledge/` subpackage. `docs.py` discovers+parses markdown (title, `[[links]]`, body) via the existing `walk_files`. `atlas.py` takes the index `DependencyGraph` + the docs and emits a pack that is a **superset of the context pack** (`to_json` output) — adding `docs` nodes + `knowledge_edges` (describes/links-to/mentions) — leaving all existing keys untouched. The HTML dashboard that renders this pack is **Plan 2**.

**Tech Stack:** Python 3.11+ stdlib only (`re`, `pathlib`, `dataclasses`); pytest.

## Global Constraints

- **Zero runtime dependencies** — pure Python 3.11+ stdlib only.
- **Deterministic** — docs sorted by `rel_path`; edges sorted; `[[link]]` resolution is first-match by normalized name with a recorded warning.
- **Backward compatible** — the atlas pack is a SUPERSET of `to_json(graph)`: every existing key/field preserved; `docs` + `knowledge_edges` + `knowledge_warnings` are ADDED. `map`/`graph`/`context`/`viz` and their JSON are unchanged; `atlas` is a new subcommand.
- **No regression** — the v1.1 suite (was 140) stays green; this plan adds its own tests.
- **`atlas` ∈ `index`** — a new `index atlas` subcommand (this plan: `--json`; Plan 2 adds `--format html`).
- **Privacy/no external** — pure local computation; no network.
- **Repo/branch** — `c:/dev/worktrees/wrm-rename`, branch `feat/v1.1-enhancements` (builds on the dashboard core @ `8ca9f0e`). Run tests: `python -m pytest tests/ --color=no -q | tail -2`.

## File structure

- Create `src/index_graph/knowledge/__init__.py` — empty package marker.
- Create `src/index_graph/knowledge/docs.py` — `Doc` dataclass + `discover_docs(root) -> list[Doc]`. Test `tests/test_docs.py`.
- Create `src/index_graph/knowledge/atlas.py` — `build_atlas_pack(graph, docs, repo_dirs) -> dict`. Test `tests/test_atlas.py`.
- Modify `src/index_graph/cli.py` — `index atlas --json`. Test `tests/test_cli_subcommands.py`.

---

### Task 1: `knowledge/docs.py` — discover + parse markdown

**Files:** Create `src/index_graph/knowledge/__init__.py` (empty), `src/index_graph/knowledge/docs.py`; Test `tests/test_docs.py`.

**Interfaces:**
- Consumes: `index_graph.graph.walk.walk_files(root, suffixes=(...))`.
- Produces: `Doc(rel_path, title, body, link_targets, dir_rel)` (frozen) and `discover_docs(root: Path) -> list[Doc]` (sorted by `rel_path`, deterministic). `link_targets` is a sorted tuple of **normalized** `[[wiki-link]]` targets.

- [ ] **Step 1: Write the failing tests** — `tests/test_docs.py`:

```python
from pathlib import Path
from index_graph.knowledge.docs import Doc, discover_docs


def _write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_discovers_markdown_sorted_with_title_and_links(tmp_path):
    _write(tmp_path, "api/README.md", "# API Gateway\n\nSee [[Auth Design]] and [[shared_utils]].\n")
    _write(tmp_path, "docs/auth.md", "no h1 here\njust prose\n")
    _write(tmp_path, "node_modules/skip.md", "# Skipped\n")  # pruned dir
    docs = discover_docs(tmp_path)
    assert [d.rel_path for d in docs] == ["api/README.md", "docs/auth.md"]  # sorted; pruned excluded
    api = docs[0]
    assert api.title == "API Gateway"               # first H1
    assert api.link_targets == ("auth-design", "shared-utils")  # normalized + sorted
    assert api.dir_rel == "api"
    auth = docs[1]
    assert auth.title == "auth"                      # filename stem when no H1
    assert auth.link_targets == ()
    assert auth.dir_rel == "docs"


def test_root_level_doc_has_empty_dir(tmp_path):
    _write(tmp_path, "OVERVIEW.md", "# Overview\n")
    d = discover_docs(tmp_path)[0]
    assert d.dir_rel == ""


def test_wikilink_alias_and_dedup(tmp_path):
    _write(tmp_path, "x.md", "[[Core|the core]] and [[core]] again, plus [[Other]].\n")
    d = discover_docs(tmp_path)[0]
    assert d.link_targets == ("core", "other")       # alias stripped, deduped, normalized, sorted
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_docs.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement** — `src/index_graph/knowledge/__init__.py` (empty file), then `src/index_graph/knowledge/docs.py`:

```python
"""Discover + parse workspace markdown into Doc nodes for the atlas."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..graph.walk import walk_files

_MD_SUFFIXES = (".md", ".markdown")
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# [[target]] or [[target|alias]] — capture target only
_WIKILINK = re.compile(r"\[\[\s*([^\]|]+?)\s*(?:\|[^\]]*)?\]\]")


def _norm(s: str) -> str:
    return s.strip().lower().replace("_", "-")


@dataclass(frozen=True)
class Doc:
    rel_path: str                  # workspace-relative, forward-slashed (stable id)
    title: str                     # first H1, else filename stem
    body: str                      # raw markdown
    link_targets: tuple[str, ...]  # normalized [[wiki-link]] targets, sorted-unique
    dir_rel: str                   # workspace-relative dir ("" at root)


def _parse_doc(rel_path: str, text: str) -> Doc:
    m = _H1.search(text)
    title = m.group(1).strip() if m else Path(rel_path).stem
    targets = tuple(sorted({_norm(t) for t in _WIKILINK.findall(text)}))
    parent = Path(rel_path).parent.as_posix()
    return Doc(rel_path, title, text, targets, "" if parent == "." else parent)


def discover_docs(root: Path) -> list[Doc]:
    """All markdown under `root` (pruned dirs excluded), as Docs sorted by rel_path."""
    out: list[Doc] = []
    for p in walk_files(root, suffixes=_MD_SUFFIXES):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append(_parse_doc(p.relative_to(root).as_posix(), text))
    out.sort(key=lambda d: d.rel_path)
    return out
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_docs.py -q` → 3 passed.

- [ ] **Step 5: Commit** — `git add src/index_graph/knowledge/__init__.py src/index_graph/knowledge/docs.py tests/test_docs.py && git commit -m "feat(atlas): discover + parse workspace markdown into Doc nodes"`

---

### Task 2: `knowledge/atlas.py` — two-layer pack (nodes + describes + links-to)

**Files:** Create `src/index_graph/knowledge/atlas.py`; Test `tests/test_atlas.py`.

**Interfaces:**
- Consumes: `Doc` (Task 1); `index_graph.context.pack.to_json(graph) -> dict` (has `repos`/`relations`/…); `index_graph.graph.build.DependencyGraph`; `normalize_name`.
- Produces: `build_atlas_pack(graph: DependencyGraph, docs: list[Doc], repo_dirs: dict[str, str]) -> dict` — `to_json(graph)` plus `pack["docs"]` (list of `{"id","title","dir"}`), `pack["knowledge_edges"]` (sorted list of `{"type","from","to","to_kind"}`), and `pack["knowledge_warnings"]` (list[str]). `repo_dirs` maps repo name → workspace-relative dir. This task implements `describes` (by location) + `links-to` (`[[link]]` resolution); Task 3 adds `mentions`.

- [ ] **Step 1: Write the failing tests** — `tests/test_atlas.py`:

```python
from index_graph.graph.build import DependencyGraph, RepoNode
from index_graph.graph.edges import Edge
from index_graph.knowledge.docs import Doc
from index_graph.knowledge.atlas import build_atlas_pack


def _graph(*names):
    repos = tuple(RepoNode(n, f"/ws/{n}", (), frozenset(), "d", frozenset()) for n in names)
    return DependencyGraph(repos, (), {n: ("library",) for n in names}, ())


def test_pack_is_superset_with_doc_nodes(tmp_path):
    g = _graph("api")
    doc = Doc("api/README.md", "API", "# API\n", (), "api")
    pack = build_atlas_pack(g, [doc], {"api": "api"})
    # existing context-pack keys preserved
    assert "relations" in pack and "roles" in pack and "repos" in pack
    # doc node added
    assert pack["docs"] == [{"id": "api/README.md", "title": "API", "dir": "api"}]


def test_describes_edge_by_location(tmp_path):
    g = _graph("api")
    doc = Doc("api/docs/auth.md", "Auth", "# Auth\n", (), "api/docs")
    pack = build_atlas_pack(g, [doc], {"api": "api"})
    assert {"type": "describes", "from": "api/docs/auth.md", "to": "api", "to_kind": "repo"} in pack["knowledge_edges"]


def test_links_to_resolves_wikilink_to_repo_and_doc():
    g = _graph("api", "core")
    a = Doc("a.md", "A", "[[core]] [[Notes]]", ("core", "notes"), "")
    notes = Doc("notes.md", "Notes", "# Notes\n", (), "")
    pack = build_atlas_pack(g, [a, notes], {"api": "api", "core": "core"})
    ke = pack["knowledge_edges"]
    assert {"type": "links-to", "from": "a.md", "to": "core", "to_kind": "repo"} in ke
    assert {"type": "links-to", "from": "a.md", "to": "notes.md", "to_kind": "doc"} in ke


def test_unresolved_wikilink_is_warned_not_an_edge():
    g = _graph("api")
    a = Doc("a.md", "A", "[[ghost]]", ("ghost",), "")
    pack = build_atlas_pack(g, [a], {"api": "api"})
    assert not any(e["type"] == "links-to" for e in pack["knowledge_edges"])
    assert any("ghost" in w for w in pack["knowledge_warnings"])


def test_knowledge_edges_sorted_deterministic():
    g = _graph("api", "core")
    a = Doc("a.md", "A", "[[core]] [[api]]", ("api", "core"), "")
    p1 = build_atlas_pack(g, [a], {"api": "api", "core": "core"})
    p2 = build_atlas_pack(g, [a], {"api": "api", "core": "core"})
    assert p1["knowledge_edges"] == p2["knowledge_edges"]
    assert p1["knowledge_edges"] == sorted(p1["knowledge_edges"], key=lambda e: (e["from"], e["type"], e["to_kind"], e["to"]))
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_atlas.py -q` → FAIL.

- [ ] **Step 3: Implement** — `src/index_graph/knowledge/atlas.py`:

```python
"""Assemble repos (index) + docs into the two-layer atlas pack."""
from __future__ import annotations

from pathlib import Path

from ..context.pack import to_json
from ..graph.build import DependencyGraph
from ..graph.resolvers.base import normalize_name
from .docs import Doc

_EDGE_SORT = lambda e: (e["from"], e["type"], e["to_kind"], e["to"])


def _target_index(repo_names, docs):
    """normalized name -> (to_kind, id); repos win over docs on collision; first doc wins."""
    idx: dict[str, tuple[str, str]] = {}
    for r in sorted(repo_names):
        idx.setdefault(normalize_name(r), ("repo", r))
    for d in docs:
        for cand in (d.title, Path(d.rel_path).stem):
            idx.setdefault(normalize_name(cand), ("doc", d.rel_path))
    return idx


def _describes(doc: Doc, repo_dirs: dict[str, str]) -> str | None:
    """The most-specific repo whose dir contains the doc's dir (by location), else None.

    A repo dir "" (repo at the workspace root) matches only a root-level doc
    (dir_rel == ""), never docs in subdirs, since the prefix branch requires
    a non-empty rdir."""
    best, best_len = None, -1
    for repo, rdir in repo_dirs.items():
        if doc.dir_rel == rdir or (rdir != "" and doc.dir_rel.startswith(rdir + "/")):
            if len(rdir) > best_len:
                best, best_len = repo, len(rdir)
    return best


def build_atlas_pack(graph: DependencyGraph, docs: list[Doc],
                     repo_dirs: dict[str, str]) -> dict:
    pack = to_json(graph)
    repo_names = {n["name"] for n in pack["repos"]}
    idx = _target_index(repo_names, docs)

    pack["docs"] = [{"id": d.rel_path, "title": d.title, "dir": d.dir_rel} for d in docs]
    edges: list[dict] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, str]] = set()      # (from, to_kind, to) — strongest wins

    def add(etype: str, frm: str, to_kind: str, to: str) -> None:
        key = (frm, to_kind, to)
        if to is None or key in seen:
            return
        seen.add(key)
        edges.append({"type": etype, "from": frm, "to": to, "to_kind": to_kind})

    # describes (by location) — strongest
    for d in docs:
        repo = _describes(d, repo_dirs)
        if repo is not None:
            add("describes", d.rel_path, "repo", repo)
    # links-to (from [[wiki-links]])
    for d in docs:
        for t in d.link_targets:
            hit = idx.get(t)
            if hit is None:
                warnings.append(f"{d.rel_path}: unresolved [[{t}]]")
                continue
            to_kind, to = hit
            if to_kind == "doc" and to == d.rel_path:
                continue                         # self-link
            add("links-to", d.rel_path, to_kind, to)

    pack["knowledge_edges"] = sorted(edges, key=_EDGE_SORT)
    pack["knowledge_warnings"] = warnings
    return pack
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_atlas.py -q` → 5 passed. (If `test_describes_edge_by_location` fails on the root-repo guard, re-read `_describes`: a doc at `api/docs` with `repo_dirs={"api":"api"}` matches via `startswith("api/")`.)

- [ ] **Step 5: Commit** — `git add src/index_graph/knowledge/atlas.py tests/test_atlas.py && git commit -m "feat(atlas): two-layer pack — doc nodes + describes + links-to edges"`

---

### Task 3: `knowledge/atlas.py` — `mentions` edges (deduped)

**Files:** Modify `src/index_graph/knowledge/atlas.py`; Test `tests/test_atlas.py`.

**Interfaces:**
- Consumes: the `build_atlas_pack` internals from Task 2 (the `add`/`seen` dedup, `idx`).
- Produces: `mentions` edges — doc→repo/doc when the target's name/title appears as a word in the doc body AND no stronger (`describes`/`links-to`) edge already connects the pair (the `seen` set enforces this).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_atlas.py`:

```python
import re as _re


def test_mentions_when_named_in_prose_and_not_already_linked():
    g = _graph("api", "core")
    # body names "core" in prose; no [[link]] / describes to core -> a mention
    a = Doc("a.md", "A", "We call into core for storage.", (), "")
    pack = build_atlas_pack(g, [a], {"api": "api", "core": "core"})
    assert {"type": "mentions", "from": "a.md", "to": "core", "to_kind": "repo"} in pack["knowledge_edges"]


def test_mention_deduped_against_stronger_edge():
    g = _graph("core")
    # both a [[link]] AND a prose mention of core -> only links-to survives (no duplicate mention)
    a = Doc("a.md", "A", "[[core]] and core again", ("core",), "")
    pack = build_atlas_pack(g, [a], {"core": "core"})
    core_edges = [e for e in pack["knowledge_edges"] if e["to"] == "core"]
    assert core_edges == [{"type": "links-to", "from": "a.md", "to": "core", "to_kind": "repo"}]


def test_mention_requires_word_boundary():
    g = _graph("api")
    # "apiary" must NOT mention "api"
    a = Doc("a.md", "A", "the apiary is unrelated", (), "")
    pack = build_atlas_pack(g, [a], {"api": "api"})
    assert not any(e["type"] == "mentions" for e in pack["knowledge_edges"])
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_atlas.py -k mention -q` → FAIL.

- [ ] **Step 3: Implement** — in `atlas.py`, add the import `import re` at the top, a helper, and a `mentions` pass after the `links-to` loop (before the `pack["knowledge_edges"] = …` line):

```python
def _mentions_name(body: str, name: str) -> bool:
    # case-insensitive whole-token match; treat '-'/'_' and spaces as separators
    pattern = r"(?<![0-9a-z])" + re.escape(name.lower()) + r"(?![0-9a-z])"
    return re.search(pattern, body.lower()) is not None
```

and the pass:

```python
    # mentions (prose name-drops) — weakest; deduped via `seen` against describes/links-to
    name_of = {("repo", r): r for r in repo_names}
    name_of.update({("doc", d.rel_path): d.title for d in docs})
    for d in docs:
        for (to_kind, to), display in sorted(name_of.items()):
            if (d.rel_path, to_kind, to) in seen:      # already a stronger edge
                continue
            if to_kind == "doc" and to == d.rel_path:
                continue
            if _mentions_name(d.body, display):       # display = repo name or doc title
                add("mentions", d.rel_path, to_kind, to)
```

(Keep the `pack["knowledge_edges"] = sorted(edges, key=_EDGE_SORT)` line after this pass.)

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_atlas.py -q` → 8 passed (5 + 3).

- [ ] **Step 5: Commit** — `git add src/index_graph/knowledge/atlas.py tests/test_atlas.py && git commit -m "feat(atlas): mentions edges (word-boundary, deduped against stronger edges)"`

---

### Task 4: `index atlas --json` CLI

**Files:** Modify `src/index_graph/cli.py`; Test `tests/test_cli_subcommands.py`.

**Interfaces:**
- Consumes: `build_atlas_pack` (Tasks 2–3), `discover_docs` (Task 1), the existing `_repo_paths(root)` + `build_graph`.
- Produces: `index atlas --root R [--json]` — builds the two-layer pack and prints it as JSON (this plan supports `--json`; without it, prints a one-line summary. `--format html` arrives in Plan 2).

- [ ] **Step 1: Write the failing test** — append to `tests/test_cli_subcommands.py`:

```python
def test_atlas_json_emits_two_layer_pack(tmp_path, capsys):
    import json
    from index_graph import cli
    # two repos with a doc that describes one and [[links]] the other
    for repo, dep in (("alpha", None), ("beta", None)):
        r = tmp_path / repo
        (r / "src" / repo).mkdir(parents=True)
        (r / "pyproject.toml").write_text(f'[project]\nname="{repo}"\n', encoding="utf-8")
        (r / "src" / repo / "__init__.py").write_text("x = 1\n", encoding="utf-8")
        (r / ".git").mkdir()
    (tmp_path / "alpha" / "DESIGN.md").write_text("# Alpha Design\n\nUses [[beta]].\n", encoding="utf-8")
    rc = cli.main(["atlas", "--root", str(tmp_path), "--json"])
    assert rc == 0
    pack = json.loads(capsys.readouterr().out)
    assert any(d["id"].endswith("DESIGN.md") for d in pack["docs"])
    ke = pack["knowledge_edges"]
    assert any(e["type"] == "describes" and e["to"] == "alpha" for e in ke)
    assert any(e["type"] == "links-to" and e["to"] == "beta" for e in ke)
    assert "relations" in pack  # superset of the context pack
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_cli_subcommands.py::test_atlas_json_emits_two_layer_pack -q` → FAIL.

- [ ] **Step 3: Implement** — in `cli.py`:
  1. add `"atlas"` to `_SUBCOMMANDS`:
     ```python
     _SUBCOMMANDS = {"map", "graph", "context", "viz", "diff", "atlas"}
     ```
  2. add the subparser in `build_parser` (after the `diff` block, before `return parser`):
     ```python
     a = sub.add_parser("atlas", help="Two-layer code + knowledge map (repos + docs).")
     a.add_argument("--root", type=Path, default=Path.cwd())
     a.add_argument("--json", action="store_true")
     ```
  3. add the handler:
     ```python
     def _cmd_atlas(args) -> int:
         from .knowledge.atlas import build_atlas_pack
         from .knowledge.docs import discover_docs
         root = args.root.resolve()
         if not root.is_dir():
             raise SystemExit(f"root not found: {root}")
         repo_paths = _repo_paths(root)

         def _rel(p: Path) -> str:
             r = p.resolve().relative_to(root).as_posix()
             return "" if r == "." else r          # a repo AT the root -> "" dir

         repo_dirs = {name: _rel(p) for name, p in repo_paths.items()}
         graph = build_graph(repo_paths)
         pack = build_atlas_pack(graph, discover_docs(root), repo_dirs)
         if args.json:
             print(json.dumps(pack, indent=2))
         else:
             print(f"repos={len(pack['repos'])} docs={len(pack['docs'])} "
                   f"knowledge_edges={len(pack['knowledge_edges'])}")
         return 0
     ```
  4. route it in `main` (before `return _cmd_map(args)`):
     ```python
     if args.cmd == "atlas":
         return _cmd_atlas(args)
     ```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_cli_subcommands.py -q` → pass. Then FULL suite `python -m pytest tests/ --color=no -q | tail -2` → all green.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(atlas): index atlas --json emits the two-layer code+knowledge pack"`

---

## Self-review notes

- **Spec coverage (engine portion):** doc nodes (Task 1), the four edge types — depends-on (inherited from `to_json`), describes/links-to (Task 2), mentions deduped (Task 3) — and the `index atlas` subcommand (Task 4). The markdown RENDERER, the HTML dashboard, clustering layout, pan/zoom, the contextualizing panel, and the synthetic demo are **Plan 2** (written against this engine's concrete pack).
- **Determinism:** docs sorted by path; `knowledge_edges` sorted by `_EDGE_SORT`; `mentions` iterate a `sorted(name_of.items())`; tests assert byte-stability.
- **Backward compat:** `build_atlas_pack` starts from `to_json(graph)` and only ADDS keys.

## Plan 2 preview (not this plan)

The follow-on plan builds the experience on this engine: fix `detail()` escaping → `knowledge/markdown.py` (zero-dep markdown→HTML + clickable `[[link]]` spans) → atlas HTML render (doc nodes + describe-clustering layout + the contextualizing panel with rendered markdown, describes, links, backlinks) → navigability (pan/zoom, unified repo+doc search, focus, nav-trail) → `index atlas --format html` + a synthetic demo + README. Writing it against this plan's real pack shape makes those tasks precise.

## Definition of done (this plan)

- `index atlas --root <ws> --json` emits a deterministic pack: the full context pack PLUS `docs` (nodes), `knowledge_edges` (describes/links-to/mentions, deduped + sorted), and `knowledge_warnings`. `--no --json` prints a one-line summary.
- All four edge types derive correctly against the fixtures; `[[link]]` resolution + mention word-boundary + dedup are tested; the pack is a verified superset of `to_json`.
- The v1.1 suite stays green; the atlas engine adds `test_docs.py` + `test_atlas.py` + the CLI test; render is deterministic.
