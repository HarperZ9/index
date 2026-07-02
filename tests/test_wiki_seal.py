"""The seal: manifest hashes + verify. A verifier that cannot fail is not a verifier."""
import json

from index_graph.certify import canonical_sha
from index_graph.wiki import build_wiki_pack, verify_wiki
from index_graph.wiki.seal import run_verify

from wiki_fixtures import make_repo, git_commit_all


def _fresh(tmp_path, name="demo"):
    root = make_repo(tmp_path / name)
    return root, build_wiki_pack(root)


def test_manifest_seals_every_page(tmp_path):
    _, pack = _fresh(tmp_path)
    manifest = pack["manifest"]
    assert manifest["schema"] == "index.wiki/1"
    listed = {p["id"]: p["sha256"] for p in manifest["pages"]}
    assert set(listed) == {p["id"] for p in pack["pages"]}
    for page in pack["pages"]:
        assert listed[page["id"]] == canonical_sha(page)
    assert manifest["inputs"]["modules"] == 4


def test_verify_match_on_untouched_wiki(tmp_path):
    root, pack = _fresh(tmp_path)
    report = verify_wiki(pack, root)
    assert report["schema"] == "index.wiki-verification/1"
    assert report["verdict"] == "MATCH"
    assert report["findings"] == []
    assert report["pages_checked"] == len(pack["pages"])
    assert report["edges_checked"] >= 2


def test_tampered_page_is_drift(tmp_path):
    root, pack = _fresh(tmp_path)
    for page in pack["pages"]:
        if page["kind"] == "module":
            page["path"] = "totally/else.py"        # tamper without re-sealing
            break
    report = verify_wiki(pack, root)
    assert report["verdict"] == "DRIFT"
    assert any(f["rule"] == "page-tampered" for f in report["findings"])


def test_forged_edge_with_consistent_hash_is_still_rejected(tmp_path):
    # The adversary re-seals the manifest after forging an edge, so the hash
    # check passes; only the graph re-derivation can catch the lie.
    root, pack = _fresh(tmp_path)
    forged = None
    for page in pack["pages"]:
        if page["kind"] == "module":
            page["imports"].append({"to": "pkg/ghost", "file": page["path"],
                                    "line": 1, "raw": "import ghost"})
            forged = page
            break
    for entry in pack["manifest"]["pages"]:
        if entry["id"] == forged["id"]:
            entry["sha256"] = canonical_sha(forged)  # consistent re-seal
    report = verify_wiki(pack, root)
    assert not any(f["rule"] == "page-tampered" for f in report["findings"])
    assert report["verdict"] == "DRIFT"
    assert any(f["rule"] == "edge-not-in-graph" for f in report["findings"])


def test_repo_moved_commit_is_drift(tmp_path):
    root = make_repo(tmp_path / "demo")
    git_commit_all(root)
    pack = build_wiki_pack(root)
    assert verify_wiki(pack, root)["verdict"] == "MATCH"
    (root / "NOTES.md").write_text("# Notes\n", encoding="utf-8")
    git_commit_all(root, "move HEAD")
    report = verify_wiki(pack, root)
    assert report["verdict"] == "DRIFT"
    assert any(f["rule"] == "commit-moved" for f in report["findings"])


def test_unverifiable_on_non_wiki_artifact(tmp_path):
    root = make_repo(tmp_path / "demo")
    assert verify_wiki({}, root)["verdict"] == "UNVERIFIABLE"
    assert verify_wiki({"schema": "index.wiki/1"}, root)["verdict"] == "UNVERIFIABLE"


def test_run_verify_reads_json_and_html_artifacts(tmp_path):
    from index_graph.wiki import render_wiki_html
    root, pack = _fresh(tmp_path)
    jpath = tmp_path / "wiki.json"
    jpath.write_text(json.dumps(pack), encoding="utf-8")
    assert run_verify(jpath, root)["verdict"] == "MATCH"
    hpath = tmp_path / "wiki.html"
    hpath.write_text(render_wiki_html(pack), encoding="utf-8")
    assert run_verify(hpath, root)["verdict"] == "MATCH"
    bad = tmp_path / "not-a-wiki.json"
    bad.write_text("{]", encoding="utf-8")
    assert run_verify(bad, root)["verdict"] == "UNVERIFIABLE"
    assert run_verify(tmp_path / "absent.json", root)["verdict"] == "UNVERIFIABLE"


def test_manifest_page_roster_mismatch_is_drift(tmp_path):
    root, pack = _fresh(tmp_path)
    dropped = pack["manifest"]["pages"].pop()        # a page the manifest no longer lists
    report = verify_wiki(pack, root)
    assert report["verdict"] == "DRIFT"
    assert any(f["rule"] == "page-unlisted" and dropped["id"] in f["detail"]
               for f in report["findings"])
    root2, pack2 = _fresh(tmp_path, "demo2")
    pack2["pages"] = [p for p in pack2["pages"] if p["id"] != "docs"]
    report2 = verify_wiki(pack2, root2)
    assert report2["verdict"] == "DRIFT"
    assert any(f["rule"] == "page-missing" for f in report2["findings"])
