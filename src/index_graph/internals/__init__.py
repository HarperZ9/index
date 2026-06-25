"""Intra-repo module graph: see inside a repo, not only repo as atom."""
from __future__ import annotations

from .modules import ModuleNode, InternalEdge, discover_modules, extract_internal_edges
from .build import InternalGraph, build_internals

__all__ = [
    "ModuleNode", "InternalEdge", "InternalGraph",
    "discover_modules", "extract_internal_edges", "build_internals",
]
