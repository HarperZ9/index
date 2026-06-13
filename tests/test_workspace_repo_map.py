from pathlib import Path

from workspace_repo_map import map


def test_default_classes_are_deterministic() -> None:
    root = Path("/tmp")
    assert map.repo_class(root / "public", root) == "public"
    assert map.repo_class(root / "state", root) == "state"
    assert map.repo_class(root / "protected", root) == "protected"


def test_root_row_to_json() -> None:
    row = map.RepoRow(
        path="x",
        relative="x",
        class_="public",
        branch="main",
        head="abc1234",
        origin="origin",
        dirty_count=0,
        untracked_count=1,
        markers=["README.md"],
    )
    payload = row.to_json()
    assert payload["class"] == "public"
    assert payload["path"] == "x"