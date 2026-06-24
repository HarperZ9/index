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
        nbrs.setdefault(e.from_repo, []).append(e.to_repo)
        nbrs.setdefault(e.to_repo, []).append(e.from_repo)
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
