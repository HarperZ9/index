"""Maps: names a model can point at, each joined to a thing the code can act on.

A map entry has three parts. The ``name`` is what a decision model answers with.
The ``description`` is the only text the model reads about the entry. The
``handle`` is what the code resolves the name to (here, a node of the outline
with its file and line span). The model never receives handles, and the code
never acts on a name it cannot resolve, so a model's answer can only select
among things that exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAP_SCHEMA = "index.map/v1"


@dataclass(frozen=True)
class MapEntry:
    name: str
    description: str
    handle: Any


class Map:
    """An ordered set of uniquely named entries."""

    def __init__(self, entries: list[MapEntry]):
        names = [e.name for e in entries]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError("map names must be unique: " + ", ".join(dupes))
        self.entries = list(entries)
        self._by_name = {e.name: e for e in entries}

    def __len__(self) -> int:
        return len(self.entries)

    def names(self) -> list[str]:
        return [e.name for e in self.entries]

    def resolve(self, name: str) -> Any:
        """The handle for ``name``. An unknown name raises; nothing is guessed."""
        if name not in self._by_name:
            raise KeyError(f"name not in map: {name!r}")
        return self._by_name[name].handle

    def for_model(self) -> list[dict]:
        """What a decision model may see: names and descriptions, never handles."""
        return [{"name": e.name, "description": e.description} for e in self.entries]

    def to_json(self, handle_view=None) -> dict:
        """Portable form. ``handle_view`` renders a handle as JSON for the code side."""
        view = handle_view or (lambda h: h)
        return {"schema": MAP_SCHEMA,
                "entries": [{"name": e.name, "description": e.description,
                             "handle": view(e.handle)} for e in self.entries]}
