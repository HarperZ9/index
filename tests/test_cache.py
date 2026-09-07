from pathlib import Path

from index_graph.cache import workspace_signature


def test_workspace_signature_ignores_nested_runtime_cache_churn(tmp_path: Path):
    scratch = tmp_path / ".scratch"
    scratch.mkdir()
    before = workspace_signature(tmp_path)

    (scratch / "probe.txt").write_text("changed unrelated runtime artifact\n", encoding="utf-8")

    assert workspace_signature(tmp_path) == before
