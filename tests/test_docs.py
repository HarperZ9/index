from pathlib import Path
from index_graph.knowledge.docs import Doc, discover_docs


def _write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_discovers_markdown_sorted_with_title_and_links(tmp_path):
    _write(tmp_path, "api/README.md", "# API Gateway\n\nSee [[Auth Design]] and [[shared_utils]].\n")
    _write(tmp_path, "docs/auth.md", "no h1 here\njust prose\n")
    _write(tmp_path, "node_modules/skip.md", "# Skipped\n")  # pruned dir
    docs = discover_docs(tmp_path)
    assert [d.rel_path for d in docs] == ["api/README.md", "docs/auth.md"]  # sorted; pruned excluded
    api = docs[0]
    assert api.title == "API Gateway"               # first H1
    assert api.link_targets == ("auth-design", "shared-utils")  # normalized + sorted
    assert api.dir_rel == "api"
    auth = docs[1]
    assert auth.title == "auth"                      # filename stem when no H1
    assert auth.link_targets == ()
    assert auth.dir_rel == "docs"


def test_root_level_doc_has_empty_dir(tmp_path):
    _write(tmp_path, "OVERVIEW.md", "# Overview\n")
    d = discover_docs(tmp_path)[0]
    assert d.dir_rel == ""


def test_wikilink_alias_and_dedup(tmp_path):
    _write(tmp_path, "x.md", "[[Core|the core]] and [[core]] again, plus [[Other]].\n")
    d = discover_docs(tmp_path)[0]
    assert d.link_targets == ("core", "other")       # alias stripped, deduped, normalized, sorted
