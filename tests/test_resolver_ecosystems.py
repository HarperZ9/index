from pathlib import Path

from index_graph.graph.build import build_graph
from index_graph.graph.resolvers import ALL_RESOLVERS

FIX = Path(__file__).parent / "fixtures"


def test_new_resolvers_registered():
    names = {r.name for r in ALL_RESOLVERS}
    assert {"csharp", "ruby", "php", "cpp"} <= names


def test_csharp_cross_repo_edge():
    g = build_graph({"App": FIX / "csharp-app", "Lib": FIX / "csharp-lib"})
    assert any(e.from_repo == "App" and e.to_repo == "Lib" for e in g.edges)


def test_ruby_cross_repo_edge():
    g = build_graph({"ruby-app": FIX / "ruby-app", "ruby-lib": FIX / "ruby-lib"})
    assert any(e.to_repo == "ruby-lib" for e in g.edges if not e.external)


def test_php_cross_repo_edge():
    g = build_graph({"org-app": FIX / "php-app", "org-lib": FIX / "php-lib"})
    assert any(e.to_repo == "org-lib" for e in g.edges if not e.external)


def test_cpp_cross_repo_edge():
    g = build_graph({"app": FIX / "cpp-app", "cpp-lib": FIX / "cpp-lib"})
    assert any(e.to_repo == "cpp-lib" for e in g.edges if not e.external)
