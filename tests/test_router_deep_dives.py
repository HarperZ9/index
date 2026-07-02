"""`index router` points agents at the verified per-repo wiki (agent stickiness)."""
from index_graph.router import render_router

_PACK = {
    "repos": [{"name": "alpha"}, {"name": "beta"}],
    "relations": [],
    "roles": {},
    "knowledge_edges": [],
    "repo_dirs": {"alpha": "alpha", "beta": "sub/beta"},
}


def test_router_lists_a_wiki_command_per_repo():
    text = render_router(_PACK)
    assert "## Per-repo deep dives" in text
    assert "`alpha`: `index wiki --root alpha`" in text
    assert "`beta`: `index wiki --root sub/beta`" in text


def test_router_omits_deep_dives_without_repo_dirs():
    pack = {k: v for k, v in _PACK.items() if k != "repo_dirs"}
    assert "Per-repo deep dives" not in render_router(pack)
