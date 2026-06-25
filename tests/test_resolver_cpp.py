from __future__ import annotations

from pathlib import Path

from index_graph.graph.resolvers.cpp import CppResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed():
    r = CppResolver()
    assert r.matches(FIX / "cpp-app") is True
    assert "cpp-lib" in r.exposed_names(FIX / "cpp-lib")


def test_raw_edges_link_and_include():
    edges = CppResolver().raw_edges(FIX / "cpp-app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("cpp-lib", "manifest") in by   # target_link_libraries
    assert ("lib.h", "import") in by        # #include "lib.h"
    # PRIVATE keyword must NOT be treated as a linked library
    assert ("PRIVATE", "manifest") not in by
