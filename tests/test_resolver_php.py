from pathlib import Path
from index_graph.graph.resolvers.php import PhpResolver

FIX = Path(__file__).parent / "fixtures"


def test_matches_and_exposed():
    r = PhpResolver()
    assert r.matches(FIX / "php-app") is True
    assert "org/lib" in r.exposed_names(FIX / "php-lib")


def test_raw_edges_manifest_and_import():
    edges = PhpResolver().raw_edges(FIX / "php-app")
    by = {(e.target_name, e.signal) for e in edges}
    assert ("org/lib", "manifest") in by    # require key
    assert ("Org", "import") in by           # use Org\Lib\Thing;  (top segment)
