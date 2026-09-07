"""Repo-level dependency inference engine."""

from __future__ import annotations

__all__ = ["DependencyGraph", "RepoNode", "build_graph"]


def __getattr__(name: str):
    if name in __all__:
        from .build import DependencyGraph, RepoNode, build_graph
        return {
            "DependencyGraph": DependencyGraph,
            "RepoNode": RepoNode,
            "build_graph": build_graph,
        }[name]
    raise AttributeError(name)
