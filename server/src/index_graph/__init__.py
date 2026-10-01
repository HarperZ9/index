"""Compact JSON repository inventory maps for multi-repo workspaces."""

from __future__ import annotations

__version__ = "2.15.0"

from .classify import classify
from .config import Config, Rule, default_config, load_config
from .model import SCHEMA_VERSION, Map, RepoRow
from .route import build_route
from .scan import build_map, discover_repos, write_map

__all__ = [
    "build_map", "write_map", "discover_repos",
    "Map", "RepoRow", "SCHEMA_VERSION",
    "Config", "Rule", "load_config", "default_config",
    "classify", "build_route", "__version__",
]
