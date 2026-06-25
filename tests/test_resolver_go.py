from __future__ import annotations

from pathlib import Path

from index_graph.graph.build import build_graph
from index_graph.graph.resolvers import ALL_RESOLVERS
from index_graph.graph.resolvers.go import GoResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed_module():
    r = GoResolver()
    assert r.matches(FIX / "go-app") is True
    assert "github.com/org/go-lib" in r.exposed_names(FIX / "go-lib")


def test_raw_edges_require_and_import():
    edges = GoResolver().raw_edges(FIX / "go-app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("github.com/org/go-lib", "manifest") in by         # from the require block
    assert ("github.com/org/go-lib/sub", "import") in by       # the sub-package import
    imp = next(e for e in edges if e.signal == "import" and e.target_name.endswith("/sub"))
    assert imp.evidence_line is not None


def test_go_cross_repo_edge_is_high_via_prefix():
    # the require (exact) and the sub-package import (prefix) merge to one high edge
    g = build_graph({"go-app": FIX / "go-app", "go-lib": FIX / "go-lib"})
    e = [x for x in g.edges if x.from_repo == "go-app" and x.to_repo == "go-lib"]
    assert len(e) == 1 and e[0].confidence == "high"


def test_go_registered():
    assert "go" in {r.name for r in ALL_RESOLVERS}
