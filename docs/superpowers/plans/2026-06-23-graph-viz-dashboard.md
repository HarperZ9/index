# Graph Visualization Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `viz/` subpackage that renders `workspace-repo-map`'s dependency graph (the `context.pack.to_json()` output) into Mermaid, a self-contained SVG network graph, an interactive single-file HTML dashboard, and compact charts, plus a `context-manifest.json` handoff -- all pure stdlib.

**Architecture:** A new `src/workspace_repo_map/viz/` subpackage consumes the existing context-pack JSON **as-is** (no change to `graph/` or `context/`). A deterministic layered-by-role layout engine (`layout.py`) produces a `LayoutModel`; `svg.py` renders it; `mermaid.py`/`charts.py`/`html.py`/`manifest.py` render from the pack JSON; `theme.py` holds shared tokens. A new `viz` CLI subcommand drives them. The hero output is the HTML dashboard, which embeds the SVG + JSON + charts and adds vanilla-JS filtering and click-to-evidence.

**Tech Stack:** Python 3.11+ (stdlib only: `json`, `hashlib`, `html`, `math`, `ast`, `dataclasses`, `pathlib`, `argparse`). pytest (optional, test-only). No third-party runtime dependencies.

## Global Constraints

- **Python floor:** `>=3.11` (already the project floor). Use `tomllib`-era stdlib freely.
- **Zero new runtime dependencies.** Every `viz/` module imports only the stdlib or `workspace_repo_map` itself. Enforced by `test_viz_boundary` (Task 10).
- **No private organ imports.** `viz/` must not import `statechain`, `provenance`, `ledger`, or `coherence_membrane`. Enforced by `test_viz_boundary` (Task 10).
- **Determinism:** every `render_*` function is a pure function of its inputs -- no wall-clock, no `random`, no host/env data, stable sorts only. Double-render must be byte-identical. (The `manifest` `generated` block is the sole exception and carries env provenance deliberately.)
- **Self-contained HTML:** the dashboard embeds all CSS/JS/SVG inline; **no `http://` or `https://` reference, no CDN `<link>`**. Fonts are CSS stacks with system fallbacks. Enforced by `test_viz_html` (Task 7).
- **No editorializing:** renderers emit only values present in the pack JSON (names, roles, confidences, evidence). No interpretive sentences. Enforced by `test_viz_editorial` (Task 10).
- **License:** MIT. Author `Zain Dana Harper`. No new file headers required beyond existing repo convention.
- **Consumes the pack shape verbatim:** `{"roles": {name: [str]}, "relations": [{"from","to","target_name","external","confidence","signals":[{"kind","file","line","raw"}]}], "salience": {name: {"in_degree","out_degree","hub"}}, "salience_audit": [...], "repos": [{"name","ecosystems","description","markers"}], "warnings": [...]}`. External edges have `"to": null`.

---

### Task 1: Theme tokens (`viz/theme.py`)

**Files:**
- Create: `src/workspace_repo_map/viz/__init__.py`
- Create: `src/workspace_repo_map/viz/theme.py`
- Test: `tests/test_viz_theme.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `THEME` (a frozen dataclass with palette + font fields); `css_variables() -> str` (a `:root{...}` CSS block); `svg_style() -> str` (a `<style>` body for inline SVG). Colors used by every renderer: `bg=#0d1b1c`, `ink=#e9e2d0`, `accent=#df5e00`, `teal=#476762`, `gold=#efab30`, `ok=#5fae93`, `muted=#8a9b92`, `hairline=rgba(239,171,48,.15)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_theme.py
from workspace_repo_map.viz.theme import THEME, css_variables, svg_style


def test_theme_has_dark_serious_palette():
    assert THEME.bg == "#0d1b1c"
    assert THEME.accent == "#df5e00"
    assert THEME.ok == "#5fae93"
    # font stacks carry system fallbacks (no external font dependency)
    assert "serif" in THEME.font_body.lower()
    assert "monospace" in THEME.font_mono.lower()


def test_css_variables_is_a_root_block_with_every_token():
    css = css_variables()
    assert css.startswith(":root{")
    for token in ("--bg", "--ink", "--accent", "--teal", "--gold", "--ok", "--muted"):
        assert token in css


def test_svg_style_references_palette_and_role_classes():
    style = svg_style()
    assert THEME.bg in style
    # one class per structural role + edge confidence classes
    for cls in (".role-entrypoint", ".role-hub", ".edge-high", ".edge-low"):
        assert cls in style
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_theme.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'workspace_repo_map.viz'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/workspace_repo_map/viz/__init__.py
"""Zero-dependency renderers for the dependency-graph context pack."""
```

```python
# src/workspace_repo_map/viz/theme.py
"""Dark Serious palette + font tokens, shared by every renderer."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    bg: str = "#0d1b1c"
    ink: str = "#e9e2d0"
    accent: str = "#df5e00"
    teal: str = "#476762"
    gold: str = "#efab30"
    ok: str = "#5fae93"
    muted: str = "#8a9b92"
    hairline: str = "rgba(239,171,48,.15)"
    font_body: str = '"EB Garamond", Georgia, serif'
    font_mono: str = '"Spline Sans Mono", ui-monospace, monospace'


THEME = Theme()

# role -> fill colour (deterministic mapping; unknown roles fall back to muted)
ROLE_COLOR = {
    "entrypoint": THEME.accent,
    "orchestrator": THEME.gold,
    "hub": THEME.ok,
    "library": THEME.teal,
    "leaf": THEME.muted,
    "isolated": THEME.muted,
    "external": THEME.hairline,
}


def css_variables() -> str:
    t = THEME
    return (
        ":root{"
        f"--bg:{t.bg};--ink:{t.ink};--accent:{t.accent};--teal:{t.teal};"
        f"--gold:{t.gold};--ok:{t.ok};--muted:{t.muted};--hairline:{t.hairline};"
        f"--font-body:{t.font_body};--font-mono:{t.font_mono};"
        "}"
    )


def svg_style() -> str:
    t = THEME
    roles = "".join(
        f".role-{role} rect{{fill:{color};}}" for role, color in ROLE_COLOR.items()
    )
    return (
        f"text{{font-family:{t.font_mono};fill:{t.ink};}}"
        f"rect{{stroke:{t.hairline};}}"
        f"{roles}"
        f".edge{{fill:none;stroke:{t.muted};}}"
        f".edge-high{{stroke:{t.ok};stroke-dasharray:none;}}"
        f".edge-moderate{{stroke:{t.gold};stroke-dasharray:5 3;}}"
        f".edge-low{{stroke:{t.muted};stroke-dasharray:2 3;}}"
        f".edge-external{{stroke:{t.hairline};}}"
        f".edge-back{{stroke:{t.accent};}}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_theme.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/viz/__init__.py src/workspace_repo_map/viz/theme.py tests/test_viz_theme.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): theme tokens (Dark Serious palette + font stacks)"
```

---

### Task 2: Layout model + layer assignment + ordering (`viz/layout.py` part 1)

**Files:**
- Create: `src/workspace_repo_map/viz/layout.py`
- Create: `tests/viz_fixtures.py`
- Test: `tests/test_viz_layout.py`

**Interfaces:**
- Consumes: the pack dict (Global Constraints).
- Produces: dataclasses `LaidNode(name, role, roles, layer, x, y, w, h, external, in_degree, out_degree, hub)`, `LaidEdge(from_repo, to_repo, confidence, external, back_edge, points, signals)`, `LayoutModel(nodes, edges, layers, width, height)`; `build_layout(pack: dict, *, include_external: bool = True) -> LayoutModel`. `ROLE_PRECEDENCE = ("entrypoint","orchestrator","hub","library","leaf","isolated")`. In this task `x/y/w/h` and `points` are populated by Task 3 -- here they default to `0.0`/empty and only `layer` + ordering are asserted.

- [ ] **Step 1: Write the failing test**

```python
# tests/viz_fixtures.py
"""Shared pack-shaped fixtures for viz tests (mirrors context.pack.to_json output)."""


def _edge(frm, to, *, target=None, external=False, confidence="high", signals=None):
    return {
        "from": frm,
        "to": to,
        "target_name": target if target is not None else (to if to else "ext"),
        "external": external,
        "confidence": confidence,
        "signals": signals or [{"kind": "import", "file": "m.py", "line": 1, "raw": "import x"}],
    }


def simple_pack():
    """web -> api -> core -> lib ; lib -> (external) requests."""
    return {
        "roles": {
            "web": ["entrypoint"],
            "api": ["orchestrator"],
            "core": ["hub"],
            "lib": ["library"],
        },
        "relations": [
            _edge("web", "api"),
            _edge("api", "core"),
            _edge("core", "lib"),
            _edge("lib", None, target="requests", external=True, confidence="moderate"),
        ],
        "salience": {
            "web": {"in_degree": 0, "out_degree": 1, "hub": False},
            "api": {"in_degree": 1, "out_degree": 1, "hub": False},
            "core": {"in_degree": 1, "out_degree": 1, "hub": True},
            "lib": {"in_degree": 1, "out_degree": 1, "hub": False},
        },
        "salience_audit": [],
        "repos": [
            {"name": "web", "ecosystems": ["python"], "description": "web app", "markers": ["entry"]},
            {"name": "api", "ecosystems": ["python"], "description": "api", "markers": []},
            {"name": "core", "ecosystems": ["python"], "description": "core", "markers": []},
            {"name": "lib", "ecosystems": ["python"], "description": "lib", "markers": ["published"]},
        ],
        "warnings": [],
    }


def cyclic_pack():
    """a -> b -> a (a cycle): forces a back-edge."""
    return {
        "roles": {"a": ["hub"], "b": ["library"]},
        "relations": [_edge("a", "b"), _edge("b", "a")],
        "salience": {
            "a": {"in_degree": 1, "out_degree": 1, "hub": True},
            "b": {"in_degree": 1, "out_degree": 1, "hub": False},
        },
        "salience_audit": [],
        "repos": [
            {"name": "a", "ecosystems": ["python"], "description": "", "markers": []},
            {"name": "b", "ecosystems": ["python"], "description": "", "markers": []},
        ],
        "warnings": [],
    }
```

```python
# tests/test_viz_layout.py
from workspace_repo_map.viz.layout import build_layout, ROLE_PRECEDENCE
from viz_fixtures import simple_pack, cyclic_pack


def _node(layout, name):
    return next(n for n in layout.nodes if n.name == name)


def test_primary_role_drives_layer_assignment():
    layout = build_layout(simple_pack())
    assert _node(layout, "web").layer == ROLE_PRECEDENCE.index("entrypoint")
    assert _node(layout, "api").layer == ROLE_PRECEDENCE.index("orchestrator")
    assert _node(layout, "core").layer == ROLE_PRECEDENCE.index("hub")
    assert _node(layout, "lib").layer == ROLE_PRECEDENCE.index("library")


def test_external_target_becomes_a_terminal_node_when_included():
    layout = build_layout(simple_pack(), include_external=True)
    ext = _node(layout, "requests")
    assert ext.external is True
    assert ext.layer == len(ROLE_PRECEDENCE)  # the terminal external band


def test_external_can_be_excluded():
    layout = build_layout(simple_pack(), include_external=False)
    assert all(n.name != "requests" for n in layout.nodes)
    assert all(not e.external for e in layout.edges)


def test_salience_is_carried_onto_nodes():
    layout = build_layout(simple_pack())
    assert _node(layout, "core").hub is True
    assert _node(layout, "api").in_degree == 1


def test_within_layer_order_is_stable_and_name_tiebroken():
    # two entrypoints, no neighbours to barycentre -> alphabetical, deterministic
    pack = simple_pack()
    pack["roles"]["aaa"] = ["entrypoint"]
    pack["repos"].append({"name": "aaa", "ecosystems": ["python"], "description": "", "markers": []})
    pack["salience"]["aaa"] = {"in_degree": 0, "out_degree": 0, "hub": False}
    layout = build_layout(pack)
    entry = [n.name for n in sorted(layout.nodes, key=lambda n: n.order) if n.layer == 0]
    assert entry == ["aaa", "web"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_layout.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'workspace_repo_map.viz.layout'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/workspace_repo_map/viz/layout.py
"""Deterministic layered-by-role layout for the dependency graph."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

ROLE_PRECEDENCE = ("entrypoint", "orchestrator", "hub", "library", "leaf", "isolated")
_EXTERNAL_LAYER = len(ROLE_PRECEDENCE)
_SWEEPS = 3


@dataclass(frozen=True)
class LaidNode:
    name: str
    role: str
    roles: tuple[str, ...]
    layer: int
    order: int = 0
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    external: bool = False
    in_degree: int = 0
    out_degree: int = 0
    hub: bool = False


@dataclass(frozen=True)
class LaidEdge:
    from_repo: str
    to_repo: str
    confidence: str
    external: bool
    back_edge: bool = False
    points: tuple[tuple[float, float], ...] = ()
    signals: tuple[dict, ...] = ()


@dataclass(frozen=True)
class LayoutModel:
    nodes: tuple[LaidNode, ...]
    edges: tuple[LaidEdge, ...]
    layers: tuple[str, ...]
    width: float = 0.0
    height: float = 0.0


def _primary_role(roles: list[str]) -> str:
    for role in ROLE_PRECEDENCE:
        if role in roles:
            return role
    return "isolated"


def _build_nodes(pack: dict, include_external: bool) -> list[LaidNode]:
    roles = pack.get("roles", {})
    salience = pack.get("salience", {})
    nodes: list[LaidNode] = []
    for repo in pack.get("repos", []):
        name = repo["name"]
        rs = tuple(roles.get(name, ()))
        primary = _primary_role(list(rs))
        sal = salience.get(name, {})
        nodes.append(
            LaidNode(
                name=name,
                role=primary,
                roles=rs,
                layer=ROLE_PRECEDENCE.index(primary),
                in_degree=int(sal.get("in_degree", 0)),
                out_degree=int(sal.get("out_degree", 0)),
                hub=bool(sal.get("hub", False)),
            )
        )
    if include_external:
        seen = set()
        for rel in pack.get("relations", []):
            if rel.get("external") and rel["target_name"] not in seen:
                seen.add(rel["target_name"])
                nodes.append(
                    LaidNode(
                        name=rel["target_name"],
                        role="external",
                        roles=("external",),
                        layer=_EXTERNAL_LAYER,
                        external=True,
                    )
                )
    return nodes


def _build_edges(pack: dict, names: set[str], include_external: bool) -> list[LaidEdge]:
    edges: list[LaidEdge] = []
    for rel in pack.get("relations", []):
        external = bool(rel.get("external"))
        target = rel["target_name"] if external else rel["to"]
        if external and not include_external:
            continue
        if target not in names:
            continue
        edges.append(
            LaidEdge(
                from_repo=rel["from"],
                to_repo=target,
                confidence=rel.get("confidence", "low"),
                external=external,
                signals=tuple(rel.get("signals", ())),
            )
        )
    return edges


def _order_within_layers(nodes: list[LaidNode], edges: list[LaidEdge]) -> list[LaidNode]:
    by_layer: dict[int, list[LaidNode]] = {}
    for n in nodes:
        by_layer.setdefault(n.layer, []).append(n)
    # initial stable order: alphabetical by name
    for layer in by_layer.values():
        layer.sort(key=lambda n: n.name)
    # adjacency for barycentre
    nbrs: dict[str, list[str]] = {n.name: [] for n in nodes}
    for e in edges:
        nbrs_setdefault = nbrs.setdefault
        nbrs_setdefault(e.from_repo, []).append(e.to_repo)
        nbrs_setdefault(e.to_repo, []).append(e.from_repo)
    for _ in range(_SWEEPS):
        pos = {n.name: i for layer in by_layer.values() for i, n in enumerate(layer)}
        for layer in by_layer.values():
            def bary(n: LaidNode) -> tuple[float, str]:
                ns = [pos[m] for m in nbrs.get(n.name, []) if m in pos]
                return (sum(ns) / len(ns) if ns else pos[n.name], n.name)
            layer.sort(key=bary)
    ordered: list[LaidNode] = []
    for layer_idx in sorted(by_layer):
        for order, n in enumerate(by_layer[layer_idx]):
            ordered.append(replace(n, order=order))
    return ordered


def build_layout(pack: dict, *, include_external: bool = True) -> LayoutModel:
    nodes = _build_nodes(pack, include_external)
    names = {n.name for n in nodes}
    edges = _build_edges(pack, names, include_external)
    nodes = _order_within_layers(nodes, edges)
    present = sorted({n.layer for n in nodes})
    labels = tuple(
        (ROLE_PRECEDENCE[i] if i < len(ROLE_PRECEDENCE) else "external") for i in present
    )
    return LayoutModel(nodes=tuple(nodes), edges=tuple(edges), layers=labels)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_layout.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/viz/layout.py tests/viz_fixtures.py tests/test_viz_layout.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): layout model, role-layer assignment, barycentre ordering"
```

---

### Task 3: Layout coordinates + edge routing + determinism (`viz/layout.py` part 2)

**Files:**
- Modify: `src/workspace_repo_map/viz/layout.py`
- Test: `tests/test_viz_layout_geometry.py`

**Interfaces:**
- Consumes: Task 2's `LayoutModel`/`LaidNode`/`LaidEdge`.
- Produces: `build_layout` now fills `x,y,w,h` on nodes (no two nodes overlap), `points` (4 cubic-bezier control points) and `back_edge` on edges, and `width`/`height` on the model. Constants `LAYER_GAP=140.0`, `NODE_H=44.0`, `NODE_GAP=28.0`, `CHAR_W=8.5`, `PAD_X=24.0`, `MARGIN=40.0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_layout_geometry.py
from workspace_repo_map.viz.layout import build_layout
from viz_fixtures import simple_pack, cyclic_pack


def _rects(layout):
    return [(n.x, n.y, n.w, n.h) for n in layout.nodes]


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def test_no_two_node_boxes_overlap():
    layout = build_layout(simple_pack())
    rects = _rects(layout)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not _overlap(rects[i], rects[j])


def test_lower_layers_sit_below_higher_layers():
    layout = build_layout(simple_pack())
    web = next(n for n in layout.nodes if n.name == "web")
    lib = next(n for n in layout.nodes if n.name == "lib")
    assert web.y < lib.y


def test_each_edge_has_four_control_points_within_canvas():
    layout = build_layout(simple_pack())
    assert layout.width > 0 and layout.height > 0
    for e in layout.edges:
        assert len(e.points) == 4
        for px, py in e.points:
            assert 0 <= px <= layout.width
            assert -1 <= py <= layout.height + 1


def test_cycle_produces_exactly_one_back_edge():
    layout = build_layout(cyclic_pack())
    backs = [e for e in layout.edges if e.back_edge]
    assert len(backs) == 1


def test_layout_is_byte_deterministic():
    a = build_layout(simple_pack())
    b = build_layout(simple_pack())
    assert a == b  # frozen dataclasses compare by value


def test_back_edge_control_points_stay_within_canvas():
    layout = build_layout(cyclic_pack())
    assert any(e.back_edge for e in layout.edges)
    for e in layout.edges:
        for px, py in e.points:
            assert 0 <= px <= layout.width
            assert -1 <= py <= layout.height + 1


def test_empty_graph_renders_a_valid_empty_canvas():
    empty = {"roles": {}, "relations": [], "salience": {},
             "salience_audit": [], "repos": [], "warnings": []}
    layout = build_layout(empty)
    assert layout.nodes == ()
    assert layout.edges == ()
    assert layout.width > 0 and layout.height > 0  # drawable empty canvas, not a crash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_layout_geometry.py -v`
Expected: FAIL -- `width` is `0`, `points` is empty, no `back_edge` set.

- [ ] **Step 3: Write minimal implementation**

Add the constants near the top of `layout.py` (under `_SWEEPS`):

```python
LAYER_GAP = 140.0
NODE_H = 44.0
NODE_GAP = 28.0
CHAR_W = 8.5
PAD_X = 24.0
MARGIN = 40.0
BACK_BOW = 60.0  # right-side headroom a back-edge bows into; reserved in the canvas
```

Add two helpers and rewrite the tail of `build_layout` to place geometry. Append to `layout.py`:

```python
def _place(nodes: list[LaidNode]) -> tuple[list[LaidNode], float, float]:
    by_layer: dict[int, list[LaidNode]] = {}
    for n in nodes:
        by_layer.setdefault(n.layer, []).append(n)
    for layer in by_layer.values():
        layer.sort(key=lambda n: n.order)
    widths = {
        idx: sum(len(n.name) * CHAR_W + PAD_X for n in layer) + NODE_GAP * (len(layer) - 1)
        for idx, layer in by_layer.items()
    }
    content_w = max(widths.values(), default=0.0)
    canvas_w = content_w + 2 * MARGIN + BACK_BOW  # reserve right headroom for back-edge bows
    placed: dict[str, LaidNode] = {}
    for layer_idx, layer in by_layer.items():
        cursor = MARGIN + (content_w - widths[layer_idx]) / 2  # centre within the content band
        y = MARGIN + layer_idx * LAYER_GAP
        for n in layer:
            w = len(n.name) * CHAR_W + PAD_X
            placed[n.name] = replace(n, x=cursor, y=y, w=w, h=NODE_H)
            cursor += w + NODE_GAP
    ordered = [placed[n.name] for n in nodes]
    layer_count = (max(by_layer) + 1) if by_layer else 0
    canvas_h = MARGIN * 2 + max(layer_count - 1, 0) * LAYER_GAP + NODE_H
    return ordered, canvas_w, canvas_h


def _route(edges: list[LaidEdge], nodes: list[LaidNode]) -> list[LaidEdge]:
    by_name = {n.name: n for n in nodes}
    routed: list[LaidEdge] = []
    for e in edges:
        src, dst = by_name.get(e.from_repo), by_name.get(e.to_repo)
        if src is None or dst is None:
            routed.append(e)
            continue
        back = dst.layer <= src.layer
        sx, sy = src.x + src.w / 2, src.y + src.h
        tx, ty = dst.x + dst.w / 2, dst.y
        if back:  # route the upward/lateral return through the reserved right headroom
            sy = src.y + src.h / 2
            ty = dst.y + dst.h / 2
            pts = ((sx, sy), (sx + BACK_BOW, sy), (tx + BACK_BOW, ty), (tx, ty))
        else:
            dy = (ty - sy) * 0.4
            pts = ((sx, sy), (sx, sy + dy), (tx, ty - dy), (tx, ty))
        routed.append(replace(e, back_edge=back, points=pts))
    return routed
```

Replace the final assembly block of `build_layout` (everything after `nodes = _order_within_layers(...)`) with:

```python
    nodes, width, height = _place(nodes)
    edges = _route(edges, nodes)
    present = sorted({n.layer for n in nodes})
    labels = tuple(
        (ROLE_PRECEDENCE[i] if i < len(ROLE_PRECEDENCE) else "external") for i in present
    )
    return LayoutModel(
        nodes=tuple(nodes), edges=tuple(edges), layers=labels, width=width, height=height
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_layout.py tests/test_viz_layout_geometry.py -v`
Expected: PASS (10 passed -- Task 2 tests still green).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/viz/layout.py tests/test_viz_layout_geometry.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): coordinate placement + bezier edge routing + back-edge detection"
```

---

### Task 4: SVG renderer (`viz/svg.py`)

**Files:**
- Create: `src/workspace_repo_map/viz/svg.py`
- Test: `tests/test_viz_svg.py`

**Interfaces:**
- Consumes: `LayoutModel` (Task 3), `THEME`/`svg_style` (Task 1).
- Produces: `render_svg(layout: LayoutModel) -> str` -- a complete, self-contained `<svg>` document string with one `<g class="node role-X" data-name data-role data-roles data-indeg data-outdeg data-hub>` per node and one `<path class="edge edge-CONF ...">` per edge carrying `data-from`, `data-to`, `data-signals` (JSON). No wall-clock.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_svg.py
import json
import xml.dom.minidom as minidom

from workspace_repo_map.viz.layout import build_layout
from workspace_repo_map.viz.svg import render_svg
from viz_fixtures import simple_pack


def test_svg_is_well_formed_xml():
    svg = render_svg(build_layout(simple_pack()))
    minidom.parseString(svg)  # raises on malformed XML
    assert svg.lstrip().startswith("<svg")


def test_every_node_and_edge_is_present():
    layout = build_layout(simple_pack())
    svg = render_svg(layout)
    for n in layout.nodes:
        assert f'data-name="{n.name}"' in svg
    # 4 relations -> 4 edge paths
    assert svg.count('class="edge') == len(layout.edges)


def test_confidence_styling_class_is_applied():
    svg = render_svg(build_layout(simple_pack()))
    assert 'class="edge edge-high"' in svg  # a rendered high edge, not merely the CSS class
    assert "edge edge-moderate" in svg       # the moderate (external) edge path


def test_edge_carries_its_witnessed_signals():
    svg = render_svg(build_layout(simple_pack()))
    assert "data-signals=" in svg
    assert "import" in svg  # the signal kind from the fixture travels into the markup


def test_render_is_deterministic():
    a = render_svg(build_layout(simple_pack()))
    b = render_svg(build_layout(simple_pack()))
    assert a == b  # pure function of input: no wall-clock, no host data
    for clock_marker in ("GMT", "UTC", "datetime"):  # no date library leaked a timestamp
        assert clock_marker not in a
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_svg.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'workspace_repo_map.viz.svg'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/workspace_repo_map/viz/svg.py
"""Render a LayoutModel to a self-contained SVG network graph."""
from __future__ import annotations

import json
from xml.sax.saxutils import escape, quoteattr

from .layout import LayoutModel
from .theme import THEME, svg_style


def _path_d(points: tuple[tuple[float, float], ...]) -> str:
    (m, c1, c2, end) = points
    return (
        f"M{m[0]:.2f},{m[1]:.2f} "
        f"C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {end[0]:.2f},{end[1]:.2f}"
    )


def _edge_svg(edge) -> str:
    classes = ["edge", f"edge-{edge.confidence}"]
    if edge.external:
        classes.append("edge-external")
    if edge.back_edge:
        classes.append("edge-back")
    sig = quoteattr(json.dumps(list(edge.signals), sort_keys=True))
    return (
        f'<path class="{" ".join(classes)}" '
        f'data-from={quoteattr(edge.from_repo)} data-to={quoteattr(edge.to_repo)} '
        f'data-signals={sig} '
        f'marker-end="url(#arrow)" d="{_path_d(edge.points)}"/>'
        if edge.points
        else ""
    )


def _node_svg(node) -> str:
    label = escape(node.name)
    return (
        f'<g class="node role-{node.role}" '
        f'data-name={quoteattr(node.name)} data-role={quoteattr(node.role)} '
        f'data-roles={quoteattr(",".join(node.roles))} '
        f'data-indeg="{node.in_degree}" data-outdeg="{node.out_degree}" '
        f'data-hub="{str(node.hub).lower()}" tabindex="0" '
        f'role="img" aria-label={quoteattr(node.name + " (" + node.role + ")")}>'
        f'<rect x="{node.x:.2f}" y="{node.y:.2f}" width="{node.w:.2f}" '
        f'height="{node.h:.2f}" rx="6"/>'
        f'<text x="{node.x + node.w / 2:.2f}" y="{node.y + node.h / 2 + 4:.2f}" '
        f'text-anchor="middle">{label}</text>'
        f"<title>{label} -- {escape(node.role)}</title>"
        f"</g>"
    )


def render_svg(layout: LayoutModel) -> str:
    defs = (
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{THEME.muted}"/></marker></defs>'
    )
    style = f"<style>{svg_style()}</style>"
    bg = f'<rect x="0" y="0" width="{layout.width:.2f}" height="{layout.height:.2f}" fill="{THEME.bg}"/>'
    edges = "".join(_edge_svg(e) for e in layout.edges)
    nodes = "".join(_node_svg(n) for n in layout.nodes)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {layout.width:.2f} {layout.height:.2f}" '
        f'width="{layout.width:.2f}" height="{layout.height:.2f}">'
        f"{defs}{style}{bg}{edges}{nodes}</svg>"
    )
```

> Note: the `xmlns="http://www.w3.org/2000/svg"` namespace literal is the one permitted `http` string (an XML namespace identifier, not a network fetch). Task 7's self-containment test allow-lists exactly this token.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_svg.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/viz/svg.py tests/test_viz_svg.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): self-contained SVG renderer with witnessed-edge data attributes"
```

---

### Task 5: Mermaid renderer (`viz/mermaid.py`)

**Files:**
- Create: `src/workspace_repo_map/viz/mermaid.py`
- Test: `tests/test_viz_mermaid.py`

**Interfaces:**
- Consumes: the pack dict; `ROLE_COLOR` (Task 1).
- Produces: `render_mermaid(pack: dict) -> str` -- a `flowchart TD` string. Internal nodes `id["name"]`, external `id(("name"))`, `classDef` per role, edges `a -->|conf| b`. Deterministic (sorted).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_mermaid.py
from workspace_repo_map.viz.mermaid import render_mermaid
from viz_fixtures import simple_pack


def test_starts_with_flowchart_td():
    assert render_mermaid(simple_pack()).splitlines()[0].strip() == "flowchart TD"


def test_every_edge_carries_confidence_and_signal_kind():
    out = render_mermaid(simple_pack())
    assert "-->|high (import)|" in out  # confidence grade + the witnessed signal kind
    assert out.count("-->") == 4  # 3 internal + 1 external edge


def test_external_dependency_uses_a_distinct_shape():
    out = render_mermaid(simple_pack())
    assert '(("requests"))' in out


def test_role_classdefs_are_emitted_and_assigned():
    out = render_mermaid(simple_pack())
    assert "classDef hub" in out
    assert "class " in out  # node-to-class assignment lines


def test_render_is_deterministic():
    assert render_mermaid(simple_pack()) == render_mermaid(simple_pack())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_mermaid.py -v`
Expected: FAIL -- module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/workspace_repo_map/viz/mermaid.py
"""Render the pack to a Mermaid flowchart (Mermaid performs its own layout)."""
from __future__ import annotations

import re

from .theme import ROLE_COLOR

_PRECEDENCE = ("entrypoint", "orchestrator", "hub", "library", "leaf", "isolated")


def _primary(roles: list[str]) -> str:
    for r in _PRECEDENCE:
        if r in roles:
            return r
    return "isolated"


def _mid(name: str) -> str:
    return "n_" + re.sub(r"[^0-9A-Za-z]", "_", name)


def render_mermaid(pack: dict) -> str:
    roles = pack.get("roles", {})
    lines = ["flowchart TD"]
    # deterministic node declarations
    internal = sorted(r["name"] for r in pack.get("repos", []))
    externals = sorted({r["target_name"] for r in pack.get("relations", []) if r.get("external")})
    node_role: dict[str, str] = {}
    for name in internal:
        primary = _primary(list(roles.get(name, ())))
        node_role[name] = primary
        lines.append(f'    {_mid(name)}["{name}"]')
    for name in externals:
        node_role[name] = "external"
        lines.append(f'    {_mid(name)}(("{name}"))')
    # edges, deterministic order
    rels = sorted(
        pack.get("relations", []),
        key=lambda r: (r["from"], r["target_name"], r.get("confidence", "")),
    )
    for r in rels:
        target = r["target_name"] if r.get("external") else r["to"]
        kinds = "+".join(sorted({s.get("kind", "") for s in r.get("signals", [])})) or "?"
        conf = r.get("confidence", "low")
        lines.append(f'    {_mid(r["from"])} -->|{conf} ({kinds})| {_mid(target)}')
    # classDefs + assignments
    for role, color in ROLE_COLOR.items():
        lines.append(f"    classDef {role} fill:{color},stroke:#0d1b1c,color:#e9e2d0;")
    for name in internal + externals:
        lines.append(f"    class {_mid(name)} {node_role[name]};")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_mermaid.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/viz/mermaid.py tests/test_viz_mermaid.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): Mermaid flowchart renderer with role classes + confidence links"
```

---

### Task 6: Charts (`viz/charts.py`)

**Files:**
- Create: `src/workspace_repo_map/viz/charts.py`
- Test: `tests/test_viz_charts.py`

**Interfaces:**
- Consumes: the pack dict.
- Produces: `render_charts(pack: dict) -> dict[str, str]` with keys `"confidence"`, `"roles"`, `"fanio"`; each value an HTML fragment string of labelled bars (`<div class="bar">` with `style="width:N%"`). Counts equal graph totals.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_charts.py
import re

from workspace_repo_map.viz.charts import render_charts
from viz_fixtures import simple_pack


def test_three_charts_returned():
    charts = render_charts(simple_pack())
    assert set(charts) == {"confidence", "roles", "fanio"}


def test_confidence_counts_sum_to_edge_total():
    charts = render_charts(simple_pack())
    counts = [int(x) for x in re.findall(r'data-count="(\d+)"', charts["confidence"])]
    assert sum(counts) == 4  # four relations in the fixture


def test_roles_chart_counts_each_primary_role_once():
    charts = render_charts(simple_pack())
    assert 'data-label="hub"' in charts["roles"]
    counts = [int(x) for x in re.findall(r'data-count="(\d+)"', charts["roles"])]
    assert sum(counts) == 4  # four internal repos


def test_fanio_lists_top_indegree_repo():
    charts = render_charts(simple_pack())
    assert "core" in charts["fanio"]  # core has the highest salience presence


def test_charts_are_deterministic():
    assert render_charts(simple_pack()) == render_charts(simple_pack())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_charts.py -v`
Expected: FAIL -- module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/workspace_repo_map/viz/charts.py
"""Three compact HTML+CSS bar charts derived purely by counting the pack."""
from __future__ import annotations

from collections import Counter
from xml.sax.saxutils import escape

_PRECEDENCE = ("entrypoint", "orchestrator", "hub", "library", "leaf", "isolated")


def _primary(roles: list[str]) -> str:
    for r in _PRECEDENCE:
        if r in roles:
            return r
    return "isolated"


def _bars(pairs: list[tuple[str, int]]) -> str:
    top = max((v for _, v in pairs), default=0) or 1
    rows = []
    for label, value in pairs:
        pct = round(100 * value / top)
        rows.append(
            f'<div class="row"><span class="lbl">{escape(label)}</span>'
            f'<span class="bar" style="width:{pct}%" data-label="{escape(label)}" '
            f'data-count="{value}"></span><span class="num">{value}</span></div>'
        )
    return '<div class="chart">' + "".join(rows) + "</div>"


def render_charts(pack: dict) -> dict[str, str]:
    rels = pack.get("relations", [])
    conf = Counter(r.get("confidence", "low") for r in rels)
    confidence = _bars([(k, conf.get(k, 0)) for k in ("high", "moderate", "low")])

    roles = pack.get("roles", {})
    role_counts = Counter(_primary(list(roles.get(r["name"], ()))) for r in pack.get("repos", []))
    role_chart = _bars([(k, role_counts[k]) for k in _PRECEDENCE if role_counts[k]])

    sal = pack.get("salience", {})
    fan_in = sorted(sal.items(), key=lambda kv: (-kv[1].get("in_degree", 0), kv[0]))[:5]
    fan_out = sorted(sal.items(), key=lambda kv: (-kv[1].get("out_degree", 0), kv[0]))[:5]
    fanio = (
        '<h4>Most depended-on</h4>'
        + _bars([(k, v.get("in_degree", 0)) for k, v in fan_in])
        + '<h4>Most dependencies</h4>'
        + _bars([(k, v.get("out_degree", 0)) for k, v in fan_out])
    )
    return {"confidence": confidence, "roles": role_chart, "fanio": fanio}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_charts.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/viz/charts.py tests/test_viz_charts.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): confidence/role/fan-in-out charts (HTML+CSS bars)"
```

---

### Task 7: HTML dashboard (`viz/html.py`)

**Files:**
- Create: `src/workspace_repo_map/viz/html.py`
- Test: `tests/test_viz_html.py`

**Interfaces:**
- Consumes: the pack dict, an SVG string (Task 4), the charts dict (Task 6), `css_variables` (Task 1).
- Produces: `render_html(pack: dict, *, svg: str, charts: dict[str, str]) -> str` -- one self-contained HTML document embedding `const DATA = <json>`, the SVG, the charts, inline CSS/JS. No external URLs except the SVG namespace literal.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_html.py
import re

from workspace_repo_map.viz.layout import build_layout
from workspace_repo_map.viz.svg import render_svg
from workspace_repo_map.viz.charts import render_charts
from workspace_repo_map.viz.html import render_html
from viz_fixtures import simple_pack


def _doc(pack):
    return render_html(pack, svg=render_svg(build_layout(pack)), charts=render_charts(pack))


def test_is_a_complete_html_document():
    doc = _doc(simple_pack())
    assert doc.lstrip().lower().startswith("<!doctype html>")
    assert "</html>" in doc


def test_embeds_data_svg_and_charts():
    doc = _doc(simple_pack())
    assert "const DATA =" in doc
    assert "<svg" in doc
    assert 'class="chart"' in doc


def test_is_self_contained_no_external_urls():
    doc = _doc(simple_pack())
    urls = re.findall(r"https?://[^\s\"')]+", doc)
    # the ONLY permitted http(s) token is the SVG XML namespace
    assert set(urls) <= {"http://www.w3.org/2000/svg"}
    assert "cdn" not in doc.lower()
    assert "<link" not in doc.lower()


def test_render_is_deterministic():
    assert _doc(simple_pack()) == _doc(simple_pack())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_html.py -v`
Expected: FAIL -- module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/workspace_repo_map/viz/html.py
"""Render the hero: a single self-contained interactive dashboard."""
from __future__ import annotations

import json

from .theme import css_variables

_CSS = """
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:var(--font-body)}main{display:grid;grid-template-columns:1fr 340px;
min-height:100vh}#stage{overflow:auto;padding:1rem}aside{border-left:1px solid
var(--hairline);padding:1rem;font-family:var(--font-mono);font-size:.82rem}
.controls{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.8rem}
.chip{cursor:pointer;border:1px solid var(--hairline);border-radius:6px;
padding:.2em .5em;background:transparent;color:var(--ink)}
.chip[aria-pressed=true]{background:var(--accent);color:var(--bg)}
input[type=search]{width:100%;padding:.4em;background:transparent;color:var(--ink);
border:1px solid var(--hairline);border-radius:6px;margin-bottom:.6rem}
.node.dim{opacity:.12}.edge.dim{opacity:.05}
.node:focus rect,.node.sel rect{stroke:var(--accent);stroke-width:2}
.row{display:flex;align-items:center;gap:.4rem;margin:.15rem 0}
.lbl{width:6.5rem;opacity:.85}.bar{height:.7rem;background:var(--teal);border-radius:3px}
.num{opacity:.7}h4{margin:.6rem 0 .2rem;color:var(--gold)}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
@media(max-width:820px){main{grid-template-columns:1fr}aside{border-left:none}}
"""

_JS = """
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const state={q:'',roles:new Set(),conf:new Set(),ext:true};
const idx={};DATA.repos.forEach(r=>idx[r.name]=r);
function match(name){const r=idx[name];if(!r)return state.ext;
 if(state.q&&!name.toLowerCase().includes(state.q))return false;
 const role=(DATA.roles[name]||['isolated'])[0];
 if(state.roles.size&&!state.roles.has(role))return false;return true;}
function apply(){$$('.node').forEach(g=>{g.classList.toggle('dim',!match(g.dataset.name));});
 $$('.edge').forEach(p=>{const on=match(p.dataset.from)&&match(p.dataset.to)&&
  (!state.conf.size||state.conf.has(p.className.baseVal.match(/edge-(high|moderate|low)/)?.[1]));
  p.classList.toggle('dim',!on);});}
function detail(name){const r=idx[name]||{name,ecosystems:[],markers:[]};
 const outs=DATA.relations.filter(e=>e.from===name);
 const ins=DATA.relations.filter(e=>e.to===name);
 const sig=e=>(e.signals||[]).map(s=>`${s.file}${s.line?':'+s.line:''} ${s.kind}`).join('; ');
 $('#detail').innerHTML=`<h3>${name}</h3><div>roles: ${(DATA.roles[name]||[]).join(', ')||'--'}</div>
 <div>in ${ (DATA.salience[name]||{}).in_degree||0 } · out ${ (DATA.salience[name]||{}).out_degree||0 }</div>
 <h4>depends on</h4>${outs.map(e=>`<div>${e.target_name} [${e.confidence}] <small>${sig(e)}</small></div>`).join('')||'--'}
 <h4>depended on by</h4>${ins.map(e=>`<div>${e.from} [${e.confidence}]</div>`).join('')||'--'}`;}
function wire(){
 $('#search').addEventListener('input',e=>{state.q=e.target.value.toLowerCase();apply();});
 $$('.chip[data-role]').forEach(c=>c.addEventListener('click',()=>{
  const r=c.dataset.role;state.roles.has(r)?state.roles.delete(r):state.roles.add(r);
  c.setAttribute('aria-pressed',state.roles.has(r));apply();}));
 $$('.node').forEach(g=>{const pick=()=>{$$('.node').forEach(n=>n.classList.remove('sel'));
  g.classList.add('sel');detail(g.dataset.name);};
  g.addEventListener('click',pick);g.addEventListener('keydown',e=>{if(e.key==='Enter')pick();});});
 apply();}
document.addEventListener('DOMContentLoaded',wire);
"""


def render_html(pack: dict, *, svg: str, charts: dict[str, str]) -> str:
    data = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    roles = sorted({(rs or ["isolated"])[0] for rs in pack.get("roles", {}).values()})
    chips = "".join(
        f'<button class="chip" data-role="{r}" aria-pressed="false">{r}</button>' for r in roles
    )
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>workspace-repo-map · context</title>"
        f"<style>{css_variables()}{_CSS}</style></head><body>"
        '<main><section id="stage">'
        f'<div class="controls"><input type="search" id="search" '
        f'placeholder="filter repos…" aria-label="filter repos">{chips}</div>'
        f"{svg}</section>"
        '<aside><div id="detail">Select a node.</div>'
        f'<h4>confidence</h4>{charts["confidence"]}'
        f'<h4>roles</h4>{charts["roles"]}'
        f'{charts["fanio"]}</aside></main>'
        f"<script>const DATA = {data};{_JS}</script>"
        "</body></html>"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_html.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/viz/html.py tests/test_viz_html.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): self-contained interactive HTML dashboard (the hero)"
```

---

### Task 8: Context manifest (`viz/manifest.py`)

**Files:**
- Create: `src/workspace_repo_map/viz/manifest.py`
- Test: `tests/test_viz_manifest.py`

**Interfaces:**
- Consumes: the pack dict.
- Produces: `render_manifest(pack: dict, *, artifacts: dict[str, bytes], meta: dict) -> dict` -- the manifest dict per the spec schema (`schema_version`, `generated`, `graph` with `snapshot_sha256`, `renders`/`context_pack` with per-artifact `sha256`, `receipts:{present:false}`). `artifacts` maps logical name (`"mermaid"`,`"svg"`,`"html"`,`"context"`) to `(path, bytes)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_manifest.py
import hashlib

from workspace_repo_map.viz.manifest import render_manifest
from viz_fixtures import simple_pack


def _artifacts():
    return {
        "mermaid": ("graph.mmd", b"flowchart TD\n"),
        "svg": ("graph.svg", b"<svg></svg>"),
        "html": ("graph.html", b"<!doctype html>"),
        "context": ("context.json", b"{}"),
    }


def test_schema_and_counts():
    m = render_manifest(simple_pack(), artifacts=_artifacts(), meta={"version": "0.4.0", "commit": "abc", "root": "/r"})
    assert m["schema_version"] == "1"
    assert m["graph"]["node_count"] == 4
    assert m["graph"]["edge_count"] == 4
    assert m["receipts"] == {"present": False}
    assert m["generated"]["version"] == "0.4.0"


def test_hashes_match_artifact_bytes():
    arts = _artifacts()
    m = render_manifest(simple_pack(), artifacts=arts, meta={"version": "0.4.0", "commit": "abc", "root": "/r"})
    assert m["renders"]["svg"]["sha256"] == hashlib.sha256(arts["svg"][1]).hexdigest()
    assert m["renders"]["svg"]["path"] == "graph.svg"
    assert m["context_pack"]["sha256"] == hashlib.sha256(arts["context"][1]).hexdigest()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_manifest.py -v`
Expected: FAIL -- module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/workspace_repo_map/viz/manifest.py
"""The context manifest: the defined handoff seam for downstream consumers."""
from __future__ import annotations

import hashlib
import json
from collections import Counter


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def render_manifest(pack: dict, *, artifacts: dict, meta: dict) -> dict:
    snapshot = json.dumps(pack, sort_keys=True, separators=(",", ":")).encode("utf-8")
    role_counts = Counter(
        (rs or ["isolated"])[0] for rs in pack.get("roles", {}).values()
    )
    renders = {
        key: {"path": path, "sha256": _sha(data)}
        for key, (path, data) in artifacts.items()
        if key in ("mermaid", "svg", "html")
    }
    out = {
        "schema_version": "1",
        "generated": {
            "tool": "workspace-repo-map",
            "version": meta.get("version", ""),
            "commit": meta.get("commit"),
            "root": meta.get("root", ""),
        },
        "graph": {
            "node_count": len(pack.get("repos", [])),
            "edge_count": len(pack.get("relations", [])),
            "roles": dict(role_counts),
            "snapshot_sha256": _sha(snapshot),
        },
        "renders": renders,
        "receipts": {"present": False},
    }
    if "context" in artifacts:
        path, data = artifacts["context"]
        out["context_pack"] = {"path": path, "sha256": _sha(data)}
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_manifest.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/viz/manifest.py tests/test_viz_manifest.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): context-manifest renderer (the handoff seam)"
```

---

### Task 9: `viz` CLI subcommand + version bump

**Files:**
- Modify: `src/workspace_repo_map/cli.py`
- Modify: `src/workspace_repo_map/__init__.py:10` (version `0.3.0` -> `0.4.0`)
- Modify: `src/workspace_repo_map/viz/__init__.py` (re-export the render functions)
- Test: `tests/test_viz_cli.py`

**Interfaces:**
- Consumes: `build_graph(_repo_paths(args.root.resolve()))` + `to_json`/`closure`/`focus_subgraph` (exactly as `_cmd_graph`/`_cmd_context` do today -- all already imported at the top of `cli.py`), plus all `viz` render functions.
- Produces: a `viz` subparser: `--root` (Path, cwd default), `--format {html,svg,mermaid,all}` (default `html`), `--focus REPO`, `--no-external`, `--out PATH`, `--out-dir DIR`. Exit `0` ok / `2` unknown focus / `1` error. (No `--map`: PR #1's graph/context scan `--root` only -- match that surface.) Re-exports in `viz/__init__.py`: `build_layout, render_svg, render_mermaid, render_charts, render_html, render_manifest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_cli.py
import json
from pathlib import Path

import pytest

from workspace_repo_map.cli import main


@pytest.fixture
def workspace(tmp_path):
    # one tiny python repo depending on a sibling lib (mirrors tests/fixtures convention)
    for name, dep in (("app", "thelib"), ("thelib", None)):
        d = tmp_path / name
        (d / "src").mkdir(parents=True)
        (d / ".git").mkdir()
        deps = f'dependencies = ["{dep}"]' if dep else "dependencies = []"
        (d / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\n{deps}\n', encoding="utf-8"
        )
        (d / "src" / "main.py").write_text(
            ("import thelib\n" if dep else "x = 1\n"), encoding="utf-8"
        )
    return tmp_path


def test_viz_html_writes_self_contained_file(workspace, tmp_path):
    out = tmp_path / "graph.html"
    rc = main(["viz", "--root", str(workspace), "--format", "html", "--out", str(out)])
    assert rc == 0
    doc = out.read_text(encoding="utf-8")
    assert doc.lstrip().lower().startswith("<!doctype html>")
    assert "https://" not in doc.replace("http://www.w3.org/2000/svg", "")


def test_viz_all_emits_every_artifact_and_manifest(workspace, tmp_path):
    out = tmp_path / "viz"
    rc = main(["viz", "--root", str(workspace), "--format", "all", "--out-dir", str(out)])
    assert rc == 0
    for f in ("graph.mmd", "graph.svg", "graph.html", "context.json", "context-manifest.json"):
        assert (out / f).exists()
    manifest = json.loads((out / "context-manifest.json").read_text(encoding="utf-8"))
    assert manifest["renders"]["svg"]["path"] == "graph.svg"


def test_unknown_focus_exits_2(workspace, tmp_path):
    rc = main(["viz", "--root", str(workspace), "--focus", "nope", "--out", str(tmp_path / "x.html")])
    assert rc == 2


def test_existing_commands_unaffected(workspace, tmp_path, capsys):
    rc = main(["graph", "--root", str(workspace), "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)  # still valid JSON


def test_version_is_0_4_0():
    from workspace_repo_map import __version__
    assert __version__ == "0.4.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_cli.py -v`
Expected: FAIL -- `viz` is not a known subcommand; version is `0.3.0`.

- [ ] **Step 3: Write minimal implementation**

Bump the version in `__init__.py` (line 10): `__version__ = "0.4.0"`.

Re-export in `viz/__init__.py` (append after the docstring):

```python
from .layout import build_layout
from .svg import render_svg
from .mermaid import render_mermaid
from .charts import render_charts
from .html import render_html
from .manifest import render_manifest

__all__ = [
    "build_layout", "render_svg", "render_mermaid",
    "render_charts", "render_html", "render_manifest",
]
```

In `cli.py`, register the subparser inside `build_parser()` (mirror the existing `context` subparser wiring) and add the handler. Add the subparser:

```python
    v = sub.add_parser("viz", help="Render the dependency graph (html/svg/mermaid).")
    v.add_argument("--root", type=Path, default=Path.cwd())
    v.add_argument("--format", choices=["html", "svg", "mermaid", "all"], default="html")
    v.add_argument("--focus", default=None)
    v.add_argument("--no-external", action="store_true")
    v.add_argument("--out", default=None)
    v.add_argument("--out-dir", default=None)
```

Add the handler (reuse the same `_graph_for(args)` helper the `graph`/`context` handlers
already use to obtain a `DependencyGraph`; if that helper is private, call it the same way
those handlers do). Insert near the other `_cmd_*` functions:

```python
def _cmd_viz(args) -> int:
    from . import viz

    graph = build_graph(_repo_paths(args.root.resolve()))
    names = {n.name for n in graph.repos}
    if args.focus:
        if args.focus not in names:
            near = [n for n in names if args.focus.lower() in n.lower()]
            print(f"unknown project: {args.focus!r}"
                  + (f" -- did you mean: {', '.join(sorted(near))}?" if near else ""))
            return 2
        graph = focus_subgraph(graph, closure(list(graph.edges), args.focus))
    pack = to_json(graph)
    include_external = not args.no_external

    def _svg() -> str:
        return viz.render_svg(viz.build_layout(pack, include_external=include_external))

    def _html() -> str:
        return viz.render_html(pack, svg=_svg(), charts=viz.render_charts(pack))

    if args.format == "all":
        out_dir = Path(args.out_dir or ".")
        out_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "graph.mmd": viz.render_mermaid(pack).encode("utf-8"),
            "graph.svg": _svg().encode("utf-8"),
            "graph.html": _html().encode("utf-8"),
            "context.json": json.dumps(pack, indent=2).encode("utf-8"),
        }
        for name, data in files.items():
            (out_dir / name).write_bytes(data)
        artifacts = {
            "mermaid": ("graph.mmd", files["graph.mmd"]),
            "svg": ("graph.svg", files["graph.svg"]),
            "html": ("graph.html", files["graph.html"]),
            "context": ("context.json", files["context.json"]),
        }
        meta = {"version": __version__, "commit": _head_commit(args.root), "root": str(args.root)}
        manifest = viz.render_manifest(pack, artifacts=artifacts, meta=meta)
        (out_dir / "context-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return 0

    text = {"svg": _svg, "mermaid": lambda: viz.render_mermaid(pack), "html": _html}[args.format]()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0
```

Add a small `_head_commit` helper (best-effort, never fatal -- keeps the run honest if git
is absent) and route `viz` in the dispatch table next to `graph`/`context`:

```python
def _head_commit(root) -> str | None:
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None
```

`cli.py` already imports `json`, `sys`, `Path`, `__version__`, `build_graph`, `_repo_paths`,
and `closure`/`focus_subgraph`/`to_json` at the top of the file -- reuse them. Two required
wirings: **(1)** add `"viz"` to the `_SUBCOMMANDS` set (line 16): `{"map", "graph", "context", "viz"}`
-- **critical**, because `main()` prepends the implicit `map` command for any `argv[0]` not in
that set, so without it `viz …` is parsed as `map viz …`. **(2)** In `main()`, beside the
existing `if args.cmd == "graph"` / `"context"` branches, add
`if args.cmd == "viz": return _cmd_viz(args)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_cli.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add src/workspace_repo_map/cli.py src/workspace_repo_map/__init__.py src/workspace_repo_map/viz/__init__.py tests/test_viz_cli.py
git -C c:/dev/worktrees/wrm-viz commit -m "feat(viz): viz CLI subcommand + version bump to 0.4.0"
```

---

### Task 10: Guardrail tests (boundary, zero-dep, no-editorializing)

**Files:**
- Test: `tests/test_viz_boundary.py`
- Test: `tests/test_viz_editorial.py`

**Interfaces:**
- Consumes: every `viz/` module (as source files + import graph).
- Produces: enforcement of three Global Constraints. No production code -- these guard the invariants.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz_boundary.py
import ast
import sys
from pathlib import Path

VIZ_DIR = Path(__file__).resolve().parents[1] / "src" / "workspace_repo_map" / "viz"
PRIVATE_ORGANS = {"statechain", "provenance", "ledger", "coherence_membrane"}
STDLIB = set(sys.stdlib_module_names)


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_no_viz_module_imports_a_private_organ():
    for path in VIZ_DIR.glob("*.py"):
        assert PRIVATE_ORGANS.isdisjoint(set(_imports(path))), path.name


def test_viz_imports_only_stdlib_or_own_package():
    allowed = STDLIB | {"workspace_repo_map"}
    for path in VIZ_DIR.glob("*.py"):
        for mod in _imports(path):
            assert mod in allowed, f"{path.name} imports third-party {mod!r}"
```

```python
# tests/test_viz_editorial.py
from workspace_repo_map.viz.svg import render_svg
from workspace_repo_map.viz.mermaid import render_mermaid
from workspace_repo_map.viz.layout import build_layout
from viz_fixtures import simple_pack

# words that would imply interpretation rather than reporting
BANNED = ("keystone", "critical", "important", "should", "recommend", "best", "worst", "elegant")


def test_renderers_do_not_editorialize():
    pack = simple_pack()
    outputs = [render_mermaid(pack), render_svg(build_layout(pack))]
    for out in outputs:
        low = out.lower()
        for word in BANNED:
            assert word not in low, f"editorializing word {word!r} leaked into output"
```

- [ ] **Step 2: Run test to verify it fails (then passes immediately if clean)**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/test_viz_boundary.py tests/test_viz_editorial.py -v`
Expected: these guard already-correct code, so they should PASS on first run. If `test_viz_imports_only_stdlib_or_own_package` fails, a `viz/` module pulled in a third-party import -- remove it. If `test_no_viz_module_imports_a_private_organ` fails, the boundary was violated -- remove the organ import.

- [ ] **Step 3: (No implementation needed -- guardrails over existing code.)**

If either test fails, fix the offending `viz/` module, not the test.

- [ ] **Step 4: Run the full viz slice**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/ -q`
Expected: the entire suite (PR #1's tests + all `test_viz_*`) passes, fast (< ~10 s).

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add tests/test_viz_boundary.py tests/test_viz_editorial.py
git -C c:/dev/worktrees/wrm-viz commit -m "test(viz): guard zero-dep, no-private-organ, no-editorializing invariants"
```

---

### Task 11: Docs + dogfood acceptance harness

**Files:**
- Modify: `CHANGELOG.md` (new `0.4.0` section)
- Modify: `USAGE.md` (document the `viz` subcommand + the three formats + the manifest)
- Modify: `README.md` (one line under features: the dashboard/graph rendering)
- Create: `scripts/viz_dogfood.py` (opt-in corpus render -- not part of the unit slice)

**Interfaces:**
- Consumes: the `viz` CLI.
- Produces: user-facing docs + a separately-invoked acceptance script that renders a real workspace and reports node/edge counts + wall time (the validation that it runs on an arbitrary corpus). No new test in the default slice.

- [ ] **Step 1: Write the dogfood harness**

```python
# scripts/viz_dogfood.py
"""Opt-in acceptance: render a real workspace and report shape + timing.

Usage: python scripts/viz_dogfood.py <root> <out-dir>
Not part of the unit slice; a manual validation that the renderers run on an
arbitrary corpus and produce a self-contained dashboard.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from workspace_repo_map.cli import main


def run(root: str, out_dir: str) -> int:
    t0 = time.perf_counter()
    rc = main(["viz", "--root", root, "--format", "all", "--out-dir", out_dir])
    dt = time.perf_counter() - t0
    html = Path(out_dir) / "graph.html"
    size = html.stat().st_size if html.exists() else 0
    print(f"rc={rc} wrote={out_dir} html_bytes={size} seconds={dt:.2f}")
    return rc


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(run(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 2: Update the docs**

Add to `CHANGELOG.md` (top, under a new heading):

```markdown
## 0.4.0

- Add `viz` subcommand: render the dependency graph as a self-contained interactive
  HTML dashboard (default), a standalone SVG network graph, or a Mermaid flowchart.
- `viz --format all` also emits `context.json` and a `context-manifest.json` handoff
  (artifact paths + content hashes) for downstream consumers.
- Renders are deterministic (byte-identical for identical input) and self-contained
  (no external URLs, no runtime dependencies).
```

In `USAGE.md`, add a `viz` section documenting the flags (`--format`, `--focus`,
`--no-external`, `--out`/`--out-dir`) and that the HTML opens directly from `file://`.
In `README.md` features, add: "Render the graph as an interactive HTML dashboard, SVG,
or Mermaid (`workspace-repo-map viz`)."

- [ ] **Step 3: Run the dogfood harness against the test fixtures**

Run: `cd c:/dev/worktrees/wrm-viz && python scripts/viz_dogfood.py tests/fixtures /tmp/wrm-viz-out`
Expected: `rc=0 ... html_bytes=<non-zero> seconds=<small>`.

- [ ] **Step 4: Run the full suite once more**

Run: `cd c:/dev/worktrees/wrm-viz && python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git -C c:/dev/worktrees/wrm-viz add CHANGELOG.md USAGE.md README.md scripts/viz_dogfood.py
git -C c:/dev/worktrees/wrm-viz commit -m "docs(viz): document the viz subcommand + add dogfood acceptance harness"
```

---

## Definition of done

- All `tests/test_viz_*` pass; PR #1's tests remain green; full slice < ~10 s.
- `workspace-repo-map viz --format html` writes a self-contained dashboard (no external URLs) that opens from `file://`.
- `viz --format all` emits svg + mermaid + html + `context.json` + `context-manifest.json` with matching content hashes.
- Double-render of any format is byte-identical.
- `test_viz_boundary` proves the public package imports no private organ and no third-party module.
- Version is `0.4.0`; CHANGELOG/USAGE/README updated.
- Open PR #2 (`feat/graph-viz`) stacked on PR #1; retarget to `main` after PR #1 merges.
