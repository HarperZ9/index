from index_graph.graph.build import DependencyGraph, RepoNode
from index_graph.graph.edges import Edge
from index_graph.knowledge.docs import Doc
from index_graph.knowledge.atlas import build_atlas_pack


def _graph(*names):
    repos = tuple(RepoNode(n, f"/ws/{n}", (), frozenset(), "d", frozenset()) for n in names)
    return DependencyGraph(repos, (), {n: ("library",) for n in names}, ())


def test_pack_is_superset_with_doc_nodes(tmp_path):
    g = _graph("api")
    doc = Doc("api/README.md", "API", "# API\n", (), "api")
    pack = build_atlas_pack(g, [doc], {"api": "api"})
    # existing context-pack keys preserved
    assert "relations" in pack and "roles" in pack and "repos" in pack
    # doc node added
    assert pack["docs"] == [{"id": "api/README.md", "title": "API", "dir": "api"}]


def test_describes_edge_by_location(tmp_path):
    g = _graph("api")
    doc = Doc("api/docs/auth.md", "Auth", "# Auth\n", (), "api/docs")
    pack = build_atlas_pack(g, [doc], {"api": "api"})
    assert {"type": "describes", "from": "api/docs/auth.md", "to": "api", "to_kind": "repo"} in pack["knowledge_edges"]


def test_links_to_resolves_wikilink_to_repo_and_doc():
    g = _graph("api", "core")
    a = Doc("a.md", "A", "[[core]] [[Notes]]", ("core", "notes"), "")
    notes = Doc("notes.md", "Notes", "# Notes\n", (), "")
    pack = build_atlas_pack(g, [a, notes], {"api": "api", "core": "core"})
    ke = pack["knowledge_edges"]
    assert {"type": "links-to", "from": "a.md", "to": "core", "to_kind": "repo"} in ke
    assert {"type": "links-to", "from": "a.md", "to": "notes.md", "to_kind": "doc"} in ke


def test_multiword_wikilink_resolves_to_titled_doc():
    g = _graph("api")
    # [[Auth Design]] (space) must resolve to the doc titled "Auth Design" — proves
    # the target index uses docs.py's _norm (space->dash), not the bare normalize_name
    a = Doc("a.md", "A", "[[Auth Design]]", ("auth-design",), "")
    design = Doc("design.md", "Auth Design", "# Auth Design\n", (), "")
    pack = build_atlas_pack(g, [a, design], {"api": "api"})
    assert {"type": "links-to", "from": "a.md", "to": "design.md", "to_kind": "doc"} in pack["knowledge_edges"]


def test_unresolved_wikilink_is_warned_not_an_edge():
    g = _graph("api")
    a = Doc("a.md", "A", "[[ghost]]", ("ghost",), "")
    pack = build_atlas_pack(g, [a], {"api": "api"})
    assert not any(e["type"] == "links-to" for e in pack["knowledge_edges"])
    assert any("ghost" in w for w in pack["knowledge_warnings"])


def test_knowledge_edges_sorted_deterministic():
    g = _graph("api", "core")
    a = Doc("a.md", "A", "[[core]] [[api]]", ("api", "core"), "")
    p1 = build_atlas_pack(g, [a], {"api": "api", "core": "core"})
    p2 = build_atlas_pack(g, [a], {"api": "api", "core": "core"})
    assert p1["knowledge_edges"] == p2["knowledge_edges"]
    assert p1["knowledge_edges"] == sorted(p1["knowledge_edges"], key=lambda e: (e["from"], e["type"], e["to_kind"], e["to"]))


import re as _re


def test_mentions_when_named_in_prose_and_not_already_linked():
    g = _graph("api", "core")
    # body names "core" in prose; no [[link]] / describes to core -> a mention
    a = Doc("a.md", "A", "We call into core for storage.", (), "")
    pack = build_atlas_pack(g, [a], {"api": "api", "core": "core"})
    assert {"type": "mentions", "from": "a.md", "to": "core", "to_kind": "repo"} in pack["knowledge_edges"]


def test_mention_deduped_against_stronger_edge():
    g = _graph("core")
    # both a [[link]] AND a prose mention of core -> only links-to survives (no duplicate mention)
    a = Doc("a.md", "A", "[[core]] and core again", ("core",), "")
    pack = build_atlas_pack(g, [a], {"core": "core"})
    core_edges = [e for e in pack["knowledge_edges"] if e["to"] == "core"]
    assert core_edges == [{"type": "links-to", "from": "a.md", "to": "core", "to_kind": "repo"}]


def test_mention_requires_word_boundary():
    g = _graph("api")
    # "apiary" must NOT mention "api"
    a = Doc("a.md", "A", "the apiary is unrelated", (), "")
    pack = build_atlas_pack(g, [a], {"api": "api"})
    assert not any(e["type"] == "mentions" for e in pack["knowledge_edges"])
