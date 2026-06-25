from __future__ import annotations

from pathlib import Path

from index_graph.graph.resolvers.csharp import CSharpResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed():
    r = CSharpResolver()
    assert r.matches(FIX / "csharp-app") is True
    assert "Lib" in r.exposed_names(FIX / "csharp-lib")


def test_raw_edges_manifest_and_import():
    edges = CSharpResolver().raw_edges(FIX / "csharp-app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("Lib", "manifest") in by             # ProjectReference -> Lib
    assert ("Newtonsoft.Json", "manifest") in by  # PackageReference
    assert ("Lib", "import") in by               # using Lib;
