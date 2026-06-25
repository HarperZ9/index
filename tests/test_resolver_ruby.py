from __future__ import annotations

from pathlib import Path

from index_graph.graph.resolvers.ruby import RubyResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed():
    r = RubyResolver()
    assert r.matches(FIX / "ruby-app") is True
    assert "ruby-lib" in r.exposed_names(FIX / "ruby-lib")


def test_raw_edges_manifest_and_import():
    edges = RubyResolver().raw_edges(FIX / "ruby-app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("ruby-lib", "manifest") in by    # gem "ruby-lib"
    assert ("ruby_lib", "import") in by       # require "ruby_lib"
