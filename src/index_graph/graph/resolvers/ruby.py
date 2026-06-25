"""Ruby ecosystem resolver: Gemfile gem declarations + require/require_relative scan."""
from __future__ import annotations

import re
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

_GEM_LINE = re.compile(r"""^\s*gem\s+['"]([^'"]+)['"]""")
_REQUIRE = re.compile(r"""^\s*require\s+['"]([^'"]+)['"]""")
_REQUIRE_RELATIVE = re.compile(r"""^\s*require_relative\s+['"]([^'"]+)['"]""")
_SPEC_NAME = re.compile(r"""(?:spec|s)\.name\s*=\s*['"]([^'"]+)['"]""")


class RubyResolver:
    name = "ruby"
    # files whose content feeds the graph (read by the freshness fingerprint)
    fingerprint_names = ("Gemfile",)
    fingerprint_suffixes = (".rb", ".gemspec")

    def matches(self, repo_root: Path) -> bool:
        if (repo_root / "Gemfile").is_file():
            return True
        return any(repo_root.glob("*.gemspec"))

    def exposed_names(self, repo_root: Path) -> set[str]:
        for gemspec in repo_root.glob("*.gemspec"):
            try:
                text = gemspec.read_text(encoding="utf-8")
            except OSError:
                continue
            m = _SPEC_NAME.search(text)
            if m:
                return {m.group(1)}
        return {repo_root.name}

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []

        # manifest edges: Gemfile
        gemfile = repo_root / "Gemfile"
        if gemfile.is_file():
            try:
                lines = gemfile.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            for i, line in enumerate(lines, 1):
                m = _GEM_LINE.match(line)
                if m:
                    gem = m.group(1)
                    edges.append(RawEdge(gem, "manifest", "Gemfile", i, line.strip()))

        # import edges: .rb source files
        for src in walk_files(repo_root, suffixes=(".rb",)):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                m = _REQUIRE.match(line)
                if m:
                    edges.append(RawEdge(m.group(1), "import", rel, i, line.strip()))
                    continue
                m = _REQUIRE_RELATIVE.match(line)
                if m:
                    edges.append(RawEdge(m.group(1), "import", rel, i, line.strip()))

        return edges
