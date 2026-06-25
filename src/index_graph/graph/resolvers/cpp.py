"""C/C++ ecosystem resolver: CMake target links + #include directives.

Best-effort only. C/C++ has no single canonical dependency manifest.
This resolver reads:
  - CMakeLists.txt for project/library/executable names (exposed_names)
  - target_link_libraries(...) for manifest edges
  - add_subdirectory(...) for manifest edges
  - #include "..." and #include <...> for import edges

Keywords PUBLIC, PRIVATE, INTERFACE in target_link_libraries are skipped;
they are not dependency targets.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..walk import walk_files
from .base import RawEdge

# CMake command patterns (case-sensitive as written in CMakeLists.txt)
_PROJECT    = re.compile(r"^\s*project\s*\(\s*([^)\s]+)", re.IGNORECASE)
_ADD_LIB    = re.compile(r"^\s*add_library\s*\(\s*([^)\s]+)", re.IGNORECASE)
_ADD_EXE    = re.compile(r"^\s*add_executable\s*\(\s*([^)\s]+)", re.IGNORECASE)
_ADD_SUBDIR = re.compile(r"^\s*add_subdirectory\s*\(\s*([^)\s]+)", re.IGNORECASE)
_TARGET_LINK = re.compile(r"^\s*target_link_libraries\s*\(", re.IGNORECASE)

# Keywords that are scope modifiers, not library names
_CMAKE_KEYWORDS = frozenset({"PUBLIC", "PRIVATE", "INTERFACE"})

# #include directives
_INCLUDE = re.compile(r'^\s*#\s*include\s*["<]([^">]+)[">]')


class CppResolver:
    name = "cpp"

    def matches(self, repo_root: Path) -> bool:
        return any(True for _ in walk_files(repo_root, names=("CMakeLists.txt",)))

    def exposed_names(self, repo_root: Path) -> set[str]:
        names: set[str] = set()
        for cmake in walk_files(repo_root, names=("CMakeLists.txt",)):
            try:
                lines = cmake.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                for pat in (_PROJECT, _ADD_LIB, _ADD_EXE):
                    m = pat.match(line)
                    if m:
                        names.add(m.group(1))
                        break
        return names

    def raw_edges(self, repo_root: Path) -> list[RawEdge]:
        edges: list[RawEdge] = []

        # Manifest edges from CMakeLists.txt
        for cmake in walk_files(repo_root, names=("CMakeLists.txt",)):
            try:
                lines = cmake.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = cmake.relative_to(repo_root).as_posix()
            i, n = 0, len(lines)
            while i < n:
                line = lines[i]
                # add_subdirectory(dir): dir is treated as a target name
                m = _ADD_SUBDIR.match(line)
                if m:
                    edges.append(RawEdge(m.group(1), "manifest", rel, i + 1, line.strip()))
                    i += 1
                    continue
                # target_link_libraries(target [PUBLIC|PRIVATE|INTERFACE] lib1 lib2 ...),
                # accumulated across lines until the closing paren (CMake spreads these).
                if _TARGET_LINK.match(line):
                    start = i
                    buf = line
                    while ")" not in buf and i + 1 < n:
                        i += 1
                        buf += " " + lines[i]
                    inner = buf.split("(", 1)[1].split(")", 1)[0]
                    toks = inner.split()
                    for token in toks[1:]:  # toks[0] is the target itself
                        if token not in _CMAKE_KEYWORDS:
                            edges.append(RawEdge(token, "manifest", rel, start + 1,
                                                 lines[start].strip()))
                    i += 1
                    continue
                i += 1

        # Import edges from C/C++ source files
        src_suffixes = (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp")
        for src in walk_files(repo_root, suffixes=src_suffixes):
            try:
                lines = src.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            rel = src.relative_to(repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                m = _INCLUDE.match(line)
                if m:
                    edges.append(RawEdge(m.group(1), "import", rel, i, line.strip()))

        return edges
