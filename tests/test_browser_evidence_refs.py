from __future__ import annotations

from index_graph.context.envelope import build_context_envelope
from index_graph.graph.build import build_graph

from test_bench import _repo


def test_context_envelope_carries_browser_evidence_refs_without_raw_dom(tmp_path):
    _repo(tmp_path / "app", "app", body_files=1)
    graph = build_graph({"app": tmp_path / "app"})

    env = build_context_envelope(
        graph,
        root=tmp_path,
        token_budget=700,
        browser_evidence_refs=[{
            "ref": "browser-evidence:fixture",
            "schema": "project-telos.browser-evidence/v1",
            "mode": "research-capture",
            "hash": "sha256:abc",
            "raw_dom": "<html>must not leak</html>",
            "screenshot_png": "must-not-leak",
        }],
    )

    assert env["schema"] == "project-telos.context-envelope/v1"
    assert env["browser_evidence_refs"] == [{
        "ref": "browser-evidence:fixture",
        "schema": "project-telos.browser-evidence/v1",
        "mode": "research-capture",
        "hash": "sha256:abc",
    }]
    assert "raw_dom" not in str(env)
    assert "screenshot_png" not in str(env)
