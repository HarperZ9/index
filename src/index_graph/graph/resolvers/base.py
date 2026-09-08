"""Resolver seam: the generic interface every ecosystem implements."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RawEdge:
    target_name: str          # name imported/declared, e.g. "requests", "@scope/pkg"
    signal: str               # "manifest" | "import"
    evidence_file: str        # repo-relative path of the witnessing file
    evidence_line: int | None # line number where cheaply known, else None
    raw_spec: str             # literal text witnessed (dep spec or import line)


def normalize_name(name: str) -> str:
    """Lowercase and unify '_'/'-' so a dist name matches an import name."""
    return name.strip().lower().replace("_", "-")


class Resolver(Protocol):
    # Optional runtime opt-in for custom resolvers. Set
    # uses_shared_source_reader = True only when every graph-relevant source read
    # goes through index_graph.graph.walk.read_source_bytes/read_source_text.
    name: str

    def matches(self, repo_root: Path) -> bool: ...
    def exposed_names(self, repo_root: Path) -> set[str]: ...
    def raw_edges(self, repo_root: Path) -> list[RawEdge]: ...
