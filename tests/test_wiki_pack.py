"""The wiki pack: pages derived from the real internals graph, nothing inferred."""
import json

from index_graph.wiki import build_wiki_pack
from index_graph.wiki.pack import CLUSTER_THRESHOLD

from wiki_fixtures import make_repo, git_commit_all


def _pages_by_id(pack: dict) -> dict:
    return {p["id"]: p for p in pack["pages"]}


def test_pack_schema_and_page_roster(tmp_path):
    pack = build_wiki_pack(make_repo(tmp_path / "demo"))
    assert pack["schema"] == "index.wiki/1"
    pages = _pages_by_id(pack)
    assert "overview" in pages
    assert "architecture" in pages
    assert "docs" in pages
    assert any(p["kind"] == "module" for p in pack["pages"])


def test_overview_carries_identity_and_inventory(tmp_path):
    root = make_repo(tmp_path / "demo")
    over = _pages_by_id(build_wiki_pack(root))["overview"]
    assert over["repo"] == "demo"
    assert over["commit"] == "unversioned"          # non-git root is stated, not guessed
    assert over["ecosystems"] == ["python"]
    assert over["module_count"] == 4                # __init__, core, api, main
    assert over["doc_count"] == 2
    assert "docs/design.md" in over["doc_paths"]
    assert "main" in over["entry_points"]           # zero fan-in, has out-edges


def test_overview_pins_the_git_commit(tmp_path):
    root = make_repo(tmp_path / "demo")
    sha = git_commit_all(root)
    pack = build_wiki_pack(root)
    assert pack["commit"] == sha
    assert _pages_by_id(pack)["overview"]["commit"] == sha
    assert pack["manifest"]["commit"] == sha


def test_module_page_edges_carry_file_line_evidence(tmp_path):
    pages = _pages_by_id(build_wiki_pack(make_repo(tmp_path / "demo")))
    api = pages["module/pkg/api"]
    assert api["path"] == "pkg/api.py"
    assert api["language"] == "python"
    imports = {(e["to"], e["file"], e["line"]) for e in api["imports"]}
    assert ("pkg/core", "pkg/api.py", 1) in imports
    dependents = {(e["from"], e["file"], e["line"]) for e in api["dependents"]}
    assert ("main", "main.py", 1) in dependents
    # the footer boundary states its own evidence count
    assert api["boundary"]["evidence_count"] == len(api["imports"]) + len(api["dependents"])
    assert api["boundary"]["generated_prose"] is False


def test_architecture_page_renders_the_real_graph(tmp_path):
    pages = _pages_by_id(build_wiki_pack(make_repo(tmp_path / "demo")))
    arch = pages["architecture"]
    assert arch["granularity"] == "module"
    assert arch["svg"].startswith("<svg")
    assert "pkg/core" in arch["svg"]
    assert "flowchart TD" in arch["mermaid"]
    assert arch["edge_count"] == 2                  # main->pkg/api, pkg/api->pkg/core
    assert arch["boundary"]["evidence_count"] == 2


def test_docs_page_is_labeled_human_authored(tmp_path):
    pages = _pages_by_id(build_wiki_pack(make_repo(tmp_path / "demo")))
    docs = pages["docs"]
    assert docs["provenance"] == "authored-by-humans"
    by_path = {d["path"]: d for d in docs["docs"]}
    assert "<h1>Demo</h1>" in by_path["README.md"]["html"]


def test_large_repo_clusters_into_packages(tmp_path):
    root = tmp_path / "big"
    pkg = root / "pile"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for i in range(CLUSTER_THRESHOLD + 1):
        (pkg / f"m{i:03d}.py").write_text("from . import m000\n" if i else "X = 1\n",
                                          encoding="utf-8")
    pack = build_wiki_pack(root)
    kinds = {p["kind"] for p in pack["pages"]}
    assert "package" in kinds and "module" not in kinds
    pile = _pages_by_id(pack)["package/pile"]
    # aggregated edges keep the module-level file:line evidence underneath
    assert pile["modules"]
    assert all(v["file"] for imp in pile["imports"] for v in imp["via"]) or pile["imports"] == []
    arch = _pages_by_id(pack)["architecture"]
    assert arch["granularity"] == "package"


def test_pack_is_deterministic_and_portable(tmp_path):
    root = make_repo(tmp_path / "demo")
    a = json.dumps(build_wiki_pack(root), sort_keys=True)
    b = json.dumps(build_wiki_pack(root), sort_keys=True)
    assert a == b
    assert str(root).replace("\\", "/") not in a.replace("\\\\", "/")  # no absolute paths
