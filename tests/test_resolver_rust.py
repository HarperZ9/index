from __future__ import annotations

from pathlib import Path

from index_graph.graph.build import build_graph
from index_graph.graph.resolvers import ALL_RESOLVERS
from index_graph.graph.resolvers.base import normalize_name
from index_graph.graph.resolvers.rust import RustResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed():
    r = RustResolver()
    assert r.matches(FIX / "rust-app") is True
    assert "rust-lib" in r.exposed_names(FIX / "rust-lib")


def test_raw_edges_manifest_and_import():
    edges = RustResolver().raw_edges(FIX / "rust-app")
    by = {(normalize_name(e.target_name), e.signal) for e in edges}
    assert ("rust-lib", "manifest") in by
    assert ("rust-lib", "import") in by                 # `use rust_lib` -> normalized rust-lib
    assert all(e.evidence_file for e in edges)
    imp = next(e for e in edges if e.signal == "import")
    assert imp.evidence_line is not None


def test_use_excludes_crate_self_super():
    targets = {normalize_name(e.target_name) for e in RustResolver().raw_edges(FIX / "rust-app")
               if e.signal == "import"}
    assert {"crate", "self", "super"}.isdisjoint(targets)


def test_rust_cross_repo_edge_is_high():
    g = build_graph({"rust-app": FIX / "rust-app", "rust-lib": FIX / "rust-lib"})
    e = [x for x in g.edges if x.from_repo == "rust-app" and x.to_repo == "rust-lib"]
    assert len(e) == 1 and e[0].confidence == "high"


def test_rust_registered():
    assert "rust" in {r.name for r in ALL_RESOLVERS}
