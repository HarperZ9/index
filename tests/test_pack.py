from __future__ import annotations

import inspect
from pathlib import Path

from workspace_repo_map.context import pack
from workspace_repo_map.context.pack import (closure, focus_subgraph, render_text,
                                             to_json)
from workspace_repo_map.graph.build import build_graph

FIX = Path(__file__).parent / "fixtures"


def _graph():
    return build_graph({"py-app": FIX / "py_app", "py-lib": FIX / "py_lib"})


def test_render_text_has_three_sections_and_evidence():
    text = render_text(_graph(), "test")
    assert "## Roles" in text and "## Relations" in text and "## Inventory" in text
    assert "py-app -> py-lib" in text


def test_to_json_carries_salience_and_audit():
    data = to_json(_graph())
    assert "salience" in data and "salience_audit" in data
    assert "relations" in data and "roles" in data


def test_closure_is_bidirectional_and_cycle_safe():
    g = _graph()
    keep = closure(list(g.edges), "py-lib")
    assert "py-app" in keep and "py-lib" in keep  # reached upstream
    sub = focus_subgraph(g, keep)
    assert {n.name for n in sub.repos} == keep


def test_no_editorializing_no_banned_phrases_in_source():
    src = inspect.getsource(pack)
    banned = ["keystone", "the heart of", "is the most important", "clearly the",
              "obviously", "the best"]
    assert not [b for b in banned if b in src.lower()]
