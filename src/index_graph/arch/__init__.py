"""Architecture criteria and the check that measures a graph against them."""
from __future__ import annotations

from .criteria import ArchitectureCriteria, ForbidRule, parse_architecture
from .check import Finding, check_graph

__all__ = [
    "ArchitectureCriteria", "ForbidRule", "parse_architecture",
    "Finding", "check_graph",
]
