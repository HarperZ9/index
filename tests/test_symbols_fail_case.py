"""Load-bearing negative test: a forged symbol call is caught as DRIFT, and the
graph derivation is byte-identical across two runs (a stable seal, no false DRIFT).

If either half fails, the verifier is not a verifier or the seal is unstable.
"""
from index_graph.certify import canonical_sha
from index_graph.symbols import build_symbol_graph, symbol_graph_to_payload
from index_graph.wiki import build_wiki_pack, verify_wiki

from symbol_fixtures import write


def test_wrong_call_is_caught_and_rerun_is_deterministic(tmp_path):
    write(tmp_path, "mod.py",
          "def func_a():\n    pass\n\n\ndef func_b():\n    func_a()\n")
    write(tmp_path, "README.md", "# demo\n")

    pack = build_wiki_pack(tmp_path)

    # FORGE: claim func_b calls a ghost function that does not exist.
    symbol_page = next(p for p in pack["pages"]
                       if p.get("kind") == "symbol" and p.get("symbol") == "mod::func_b")
    symbol_page["callees"].append({"to_symbol": "mod::ghost_function",
                                   "file": "mod.py", "line": 6, "raw": "ghost_function()"})

    # Re-seal the manifest so the page-hash check passes; only re-derivation catches it.
    for entry in pack["manifest"]["pages"]:
        if entry["id"] == symbol_page["id"]:
            entry["sha256"] = canonical_sha(symbol_page)

    report = verify_wiki(pack, tmp_path)
    assert report["verdict"] == "DRIFT", f"expected DRIFT, got {report['verdict']}"
    assert any(f["rule"] == "symbol-call-not-in-graph" for f in report["findings"]), \
        report["findings"]

    # Determinism: two runs produce a byte-identical graph payload (stable seal).
    g1 = build_symbol_graph(tmp_path)
    g2 = build_symbol_graph(tmp_path)
    assert canonical_sha(symbol_graph_to_payload(g1)) == canonical_sha(symbol_graph_to_payload(g2))
