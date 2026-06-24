from __future__ import annotations

from pathlib import Path

from index_graph.graph.resolvers import ALL_RESOLVERS
from index_graph.graph.resolvers.javascript import JavaScriptResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed_name():
    r = JavaScriptResolver()
    assert r.matches(FIX / "js-app") is True
    assert "@acme/js-lib" in r.exposed_names(FIX / "js-lib")


def test_raw_edges_manifest_and_import_skip_relative():
    edges = JavaScriptResolver().raw_edges(FIX / "js-app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("@acme/js-lib", "manifest") in by
    assert ("@acme/js-lib", "import") in by
    # relative require("./local") is intra-repo -> never emitted
    assert all(not e.target_name.startswith(".") for e in edges)


def test_registry_contains_both_resolvers():
    names = {r.name for r in ALL_RESOLVERS}
    assert {"python", "javascript"} <= names
