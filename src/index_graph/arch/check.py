"""Measure a graph against an ArchitectureCriteria; produce evidence-bearing findings.

`glob_to_regex` is imported lazily inside the matcher so this module can be
imported from config.py without a circular import.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .criteria import ArchitectureCriteria


@dataclass(frozen=True)
class Finding:
    rule: str
    detail: str
    edge: str | None
    evidence: str | None


def _match(glob: str, name: str) -> bool:
    from ..config import glob_to_regex
    return re.match(glob_to_regex(glob), name) is not None


def _first_evidence(rel: dict) -> str | None:
    sigs = rel.get("signals") or []
    if not sigs:
        return None
    s = sigs[0]
    f = s.get("file")
    if not f:
        return None
    line = s.get("line")
    return f"{f}:{line}" if line is not None else f


def _layer_of(name: str, layers: tuple[str, ...]) -> int | None:
    for i, layer in enumerate(layers):
        if (name == layer or name.startswith(layer + "/")
                or _match(f"{layer}/**", name) or _match(f"**/{layer}", name)):
            return i
    return None


def check_graph(pack: dict, criteria: ArchitectureCriteria) -> list[Finding]:
    findings: list[Finding] = []
    relations = [r for r in pack.get("relations", []) if not r.get("external")]

    # forbidden edges
    for rule in criteria.forbid:
        for r in relations:
            frm, to = r.get("from"), r.get("to")
            if to and _match(rule.from_glob, frm) and _match(rule.to_glob, to):
                findings.append(Finding(
                    "forbid", f"{rule.from_glob} must not depend on {rule.to_glob}",
                    f"{frm} -> {to}", _first_evidence(r)))

    # layers: lower index = lower layer; an edge from lower to higher is a violation
    if criteria.layers:
        for r in relations:
            frm, to = r.get("from"), r.get("to")
            if not to:
                continue
            li, lj = _layer_of(frm, criteria.layers), _layer_of(to, criteria.layers)
            if li is not None and lj is not None and li < lj:
                findings.append(Finding(
                    "layer",
                    f"{criteria.layers[li]} must not depend upward on {criteria.layers[lj]}",
                    f"{frm} -> {to}", _first_evidence(r)))

    # cycle ceiling
    if criteria.max_cycles is not None:
        n = len(pack.get("cycles", []))
        if n > criteria.max_cycles:
            findings.append(Finding(
                "max_cycles",
                f"{n} dependency cycle(s) exceed the ceiling of {criteria.max_cycles}",
                None, None))

    # ownership: a declared owner glob that matches no repo is a finding
    if criteria.owns:
        names_src = [r.get("from") for r in pack.get("relations", [])]
        names_src += [r.get("to") for r in pack.get("relations", []) if r.get("to")]
        names_src += list(pack.get("roles", {}).keys())
        names = sorted({n for n in names_src if n})
        for glob, owner in criteria.owns:
            if not any(_match(glob, n) for n in names):
                findings.append(Finding(
                    "owns", f"ownership glob {glob} ({owner}) matches no repo", None, None))

    # required edges (Reflexion absence): an intended dependency that is not realized
    for rule in criteria.require:
        present = any(
            r.get("to") and _match(rule.from_glob, r.get("from")) and _match(rule.to_glob, r.get("to"))
            for r in relations)
        if not present:
            findings.append(Finding(
                "absence", f"{rule.from_glob} should depend on {rule.to_glob} but does not",
                None, None))

    return sorted(findings, key=lambda f: (f.rule, f.edge or "", f.detail))
