"""Symbol pages are sealed and re-checked in verify_wiki alongside module edges."""
from index_graph.certify import canonical_sha
from index_graph.wiki import build_wiki_pack, verify_wiki

from symbol_fixtures import write


def _repo(root):
    write(root, "pkg/__init__.py", "")
    write(root, "pkg/core.py",
          "def helper():\n    pass\n\n\ndef run():\n    helper()\n")
    write(root, "README.md", "# Demo\n")
    return root


def test_symbol_pages_present_and_verify_match(tmp_path):
    root = _repo(tmp_path)
    pack = build_wiki_pack(root)
    symbol_pages = [p for p in pack["pages"] if p.get("kind") == "symbol"]
    assert symbol_pages
    report = verify_wiki(pack, root)
    assert report["verdict"] == "MATCH", report["findings"]


def test_symbol_page_records_callers_with_evidence(tmp_path):
    root = _repo(tmp_path)
    pack = build_wiki_pack(root)
    helper_page = next(p for p in pack["pages"]
                       if p.get("kind") == "symbol" and p.get("symbol") == "pkg/core::helper")
    assert helper_page["callers"]
    caller = helper_page["callers"][0]
    assert caller["from_symbol"] == "pkg/core::run"
    assert caller["file"] == "pkg/core.py"
    assert isinstance(caller["line"], int)


def test_forged_symbol_caller_is_drift(tmp_path):
    # Re-seal the manifest so the page hash is consistent; only graph
    # re-derivation can catch the forged edge.
    root = _repo(tmp_path)
    pack = build_wiki_pack(root)
    forged = None
    for page in pack["pages"]:
        if page.get("kind") == "symbol" and page.get("symbol") == "pkg/core::helper":
            page["callers"].append({"from_symbol": "ghost::phantom",
                                    "file": "ghost.py", "line": 99, "raw": "helper()"})
            forged = page
            break
    for entry in pack["manifest"]["pages"]:
        if entry["id"] == forged["id"]:
            entry["sha256"] = canonical_sha(forged)
    report = verify_wiki(pack, root)
    assert not any(f["rule"] == "page-tampered" for f in report["findings"])
    assert report["verdict"] == "DRIFT"
    assert any(f["rule"] == "symbol-call-not-in-graph" for f in report["findings"])


def test_forged_symbol_callee_is_drift(tmp_path):
    root = _repo(tmp_path)
    pack = build_wiki_pack(root)
    forged = None
    for page in pack["pages"]:
        if page.get("kind") == "symbol" and page.get("symbol") == "pkg/core::run":
            page["callees"].append({"to_symbol": "pkg/core::nonexistent",
                                    "file": "pkg/core.py", "line": 6, "raw": "nonexistent()"})
            forged = page
            break
    for entry in pack["manifest"]["pages"]:
        if entry["id"] == forged["id"]:
            entry["sha256"] = canonical_sha(forged)
    report = verify_wiki(pack, root)
    assert report["verdict"] == "DRIFT"
    assert any(f["rule"] == "symbol-call-not-in-graph" for f in report["findings"])


def test_symbol_pages_omitted_above_limit_but_still_verifies(tmp_path, monkeypatch):
    # Above the per-symbol-page limit the pack omits symbol pages (no bloat),
    # yet the module wiki still seals and verifies MATCH.
    import index_graph.wiki.pack as pack_mod
    monkeypatch.setattr(pack_mod, "SYMBOL_PAGE_LIMIT", 1)
    write(tmp_path, "mod.py",
          "def foo():\n    pass\n\n\ndef bar():\n    foo()\n\n\ndef baz():\n    pass\n")
    write(tmp_path, "README.md", "# demo\n")
    pack = pack_mod.build_wiki_pack(tmp_path)
    assert not [p for p in pack["pages"] if p.get("kind") == "symbol"]
    assert verify_wiki(pack, tmp_path)["verdict"] == "MATCH"


def test_unresolved_calls_do_not_cause_false_drift(tmp_path):
    write(tmp_path, "mod.py", "def foo():\n    undefined_func()\n")
    write(tmp_path, "README.md", "# demo\n")
    pack = build_wiki_pack(tmp_path)
    report = verify_wiki(pack, tmp_path)
    assert report["verdict"] == "MATCH", report["findings"]
