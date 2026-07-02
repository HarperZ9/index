"""The wiki HTML artifact: self-contained, hostile-input-safe, honestly footered."""
from index_graph.wiki import build_wiki_pack, render_wiki_html

from wiki_fixtures import make_repo


def test_html_is_self_contained(tmp_path):
    doc = render_wiki_html(build_wiki_pack(make_repo(tmp_path / "demo")))
    low = doc.lower()
    assert "<script src" not in low          # no external scripts
    assert "<link " not in low               # no external stylesheets or fonts
    assert "@import" not in low
    assert doc.startswith("<!doctype html>")


def test_every_page_footer_states_the_derivation_boundary(tmp_path):
    pack = build_wiki_pack(make_repo(tmp_path / "demo"))
    doc = render_wiki_html(pack)
    assert doc.count("structure derived from the dependency graph") == len(pack["pages"])
    assert doc.count("no generated prose") == len(pack["pages"])
    assert "evidence shown: 2 file:line reference(s)" in doc  # pkg/api: 1 import + 1 dependent
    assert "authored by humans" in doc                        # the docs page label


def test_hostile_markdown_cannot_break_out(tmp_path):
    root = make_repo(tmp_path / "demo")
    (root / "EVIL.md").write_text(
        "# Pwn\n\n<script>alert(1)</script> and `</script>` and "
        '<img src=x onerror="alert(2)">\n', encoding="utf-8")
    doc = render_wiki_html(build_wiki_pack(root))
    # exactly the real closing tags: the embedded JSON data island + the nav script
    assert doc.count("</script>") == 2
    assert "onerror=" not in doc.replace("onerror=&quot;", "")
    assert "<img src=x" not in doc


def test_hostile_module_name_is_escaped(tmp_path):
    from index_graph.wiki.html import render_wiki_html as render
    pack = build_wiki_pack(make_repo(tmp_path / "demo"))
    for page in pack["pages"]:
        if page["kind"] == "module":
            page["title"] = '<img src=x onerror=alert(1)>'
            break
    doc = render(pack)
    assert "<img src=x" not in doc
    assert "&lt;img src=x" in doc


def test_html_embeds_the_sealed_pack_for_verification(tmp_path):
    from index_graph.wiki.seal import extract_embedded_pack
    pack = build_wiki_pack(make_repo(tmp_path / "demo"))
    doc = render_wiki_html(pack)
    assert extract_embedded_pack(doc) == pack


def test_html_render_is_deterministic(tmp_path):
    root = make_repo(tmp_path / "demo")
    assert (render_wiki_html(build_wiki_pack(root))
            == render_wiki_html(build_wiki_pack(root)))


def test_nav_lists_every_page_once(tmp_path):
    pack = build_wiki_pack(make_repo(tmp_path / "demo"))
    doc = render_wiki_html(pack)
    for i in range(len(pack["pages"])):
        assert f'data-target="page-{i}"' in doc
        assert f'id="page-{i}"' in doc
