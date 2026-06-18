"""Pure data model for a workspace repository map. No I/O, git, or config."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RepoRow:
    path: str
    class_: str
    branch: str
    head: str
    origin: str
    dirty_count: int
    untracked_count: int
    markers: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "class": self.class_,
            "branch": self.branch,
            "head": self.head,
            "origin": self.origin,
            "dirty_count": self.dirty_count,
            "untracked_count": self.untracked_count,
            "markers": list(self.markers),
        }


@dataclass(frozen=True)
class Map:
    schema_version: int
    tool_version: str
    generated_at: str
    root_sha256_prefix: str
    root: str | None
    absolute_paths_included: bool
    repo_count: int
    dirty_count: int
    class_counts: dict[str, int]
    top_level: tuple[dict[str, Any], ...]
    repositories: tuple[RepoRow, ...]
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "generated_at": self.generated_at,
            "root_sha256_prefix": self.root_sha256_prefix,
            "absolute_paths_included": self.absolute_paths_included,
            "repo_count": self.repo_count,
            "dirty_count": self.dirty_count,
            "class_counts": self.class_counts,
            "top_level": list(self.top_level),
            "repositories": [row.to_json() for row in self.repositories],
        }
        if self.root is not None:
            data["root"] = self.root
        if self.annotations:
            data["annotations"] = self.annotations
        return data
