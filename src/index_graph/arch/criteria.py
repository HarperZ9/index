"""The architecture criterion: a rule the graph is measured against.

This module imports nothing from the rest of the package so that config.py can
import it without a cycle. The check that consumes a criterion lives in check.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForbidRule:
    from_glob: str
    to_glob: str


@dataclass(frozen=True)
class RequireRule:
    """An intended dependency that must be realized. A missing one is an
    'absence' in Reflexion-model conformance (the architecture you declared is
    not the one the code actually built)."""
    from_glob: str
    to_glob: str


@dataclass(frozen=True)
class ArchitectureCriteria:
    layers: tuple[str, ...] = ()
    forbid: tuple[ForbidRule, ...] = ()
    max_cycles: int | None = None
    owns: tuple[tuple[str, str], ...] = ()
    require: tuple[RequireRule, ...] = ()

    @property
    def declared(self) -> bool:
        return bool(self.layers or self.forbid or self.require
                    or self.max_cycles is not None or self.owns)


def parse_architecture(data: dict) -> ArchitectureCriteria:
    """Parse the [architecture] TOML block. Raises SystemExit on malformed input."""
    layers = tuple(str(x) for x in data.get("layers", []))

    forbid: list[ForbidRule] = []
    for idx, item in enumerate(data.get("forbid", [])):
        if not isinstance(item, dict) or "from" not in item or "to" not in item:
            raise SystemExit(f"[architecture] forbid[{idx}] requires 'from' and 'to'")
        forbid.append(ForbidRule(str(item["from"]), str(item["to"])))

    require: list[RequireRule] = []
    for idx, item in enumerate(data.get("require", [])):
        if not isinstance(item, dict) or "from" not in item or "to" not in item:
            raise SystemExit(f"[architecture] require[{idx}] requires 'from' and 'to'")
        require.append(RequireRule(str(item["from"]), str(item["to"])))

    mc = data.get("max_cycles", None)
    if mc is not None and (isinstance(mc, bool) or not isinstance(mc, int) or mc < 0):
        raise SystemExit("[architecture] max_cycles must be a non-negative integer")

    owns_raw = data.get("owns", {})
    if not isinstance(owns_raw, dict):
        raise SystemExit("[architecture] owns must be a table of glob = owner")
    owns = tuple(sorted((str(k), str(v)) for k, v in owns_raw.items()))

    return ArchitectureCriteria(layers, tuple(forbid), mc, owns, tuple(require))
