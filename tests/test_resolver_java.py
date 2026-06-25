from __future__ import annotations

from pathlib import Path

from index_graph.graph.build import build_graph
from index_graph.graph.resolvers import ALL_RESOLVERS
from index_graph.graph.resolvers.java import JavaResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_pom_and_gradle():
    r = JavaResolver()
    assert r.matches(FIX / "java-app") is True
    assert r.matches(FIX / "gradle-app") is True


def test_exposed_coordinates_from_pom():
    assert "com.example:java-lib" in JavaResolver().exposed_names(FIX / "java-lib")


def test_maven_dependency_edge():
    by = {(e.target_name, e.signal) for e in JavaResolver().raw_edges(FIX / "java-app")}
    assert ("com.example:java-lib", "manifest") in by


def test_gradle_dependency_edge():
    by = {(e.target_name, e.signal) for e in JavaResolver().raw_edges(FIX / "gradle-app")}
    assert ("com.example:java-lib", "manifest") in by


def test_java_cross_repo_edge_is_moderate():
    g = build_graph({"java-app": FIX / "java-app", "java-lib": FIX / "java-lib"})
    e = [x for x in g.edges if x.from_repo == "java-app" and x.to_repo == "java-lib"]
    assert len(e) == 1 and e[0].confidence == "moderate"     # manifest-only


def test_java_registered():
    assert "java" in {r.name for r in ALL_RESOLVERS}
