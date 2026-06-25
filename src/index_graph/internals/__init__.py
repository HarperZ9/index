"""Intra-repo module graph: see inside a repo, not only repo as atom."""
from __future__ import annotations

from .modules import ModuleNode, InternalEdge, Unresolved, discover_modules, extract_internal_edges
from .build import InternalGraph, Coverage, build_internals

__all__ = [
    "ModuleNode", "InternalEdge", "Unresolved", "InternalGraph", "Coverage",
    "discover_modules", "extract_internal_edges", "build_internals",
]
