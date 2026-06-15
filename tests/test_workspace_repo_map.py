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


def test_build_map_omits_absolute_paths(tmp_path: Path) -> None:
    public_repo = tmp_path / "public" / "demo"
    protected_repo = tmp_path / "protected" / "secret"
    (public_repo / ".git").mkdir(parents=True)
    (protected_repo / ".git").mkdir(parents=True)

    payload = map.build_map(tmp_path)
    encoded = map.json.dumps(payload)

    assert payload["root"] == "<local-root>"
    assert payload["absolute_paths_included"] is False
    assert str(tmp_path) not in encoded
    assert payload["protected_policy"]["path"] == "protected"
    assert "public/demo" in encoded


def test_sanitize_origin_redacts_credentials_and_protected_origins() -> None:
    assert map.sanitize_origin(
        "https://token@example.com/owner/repo.git",
        "public",
    ) == "https://<redacted>@example.com/owner/repo.git"
    assert map.sanitize_origin(
        "https://example.com/owner/repo.git?token=abc123",
        "public",
    ) == "https://example.com/owner/repo.git?token=<redacted>"
    assert map.sanitize_origin(
        "git@example.com:owner/private.git",
        "protected",
    ) == "<protected-origin-omitted>"
