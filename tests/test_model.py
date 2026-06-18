from workspace_repo_map.model import Map, RepoRow, SCHEMA_VERSION


def _row(**over):
    base = dict(path="public/demo", class_="public", branch="main", head="abc1234",
                origin="https://github.com/o/r.git", dirty_count=0, untracked_count=1,
                markers=("README.md",))
    base.update(over)
    return RepoRow(**base)


def test_reporow_to_json_maps_class_and_lists_markers():
    data = _row().to_json()
    assert data["class"] == "public"
    assert "class_" not in data
    assert data["markers"] == ["README.md"]


def _map(**over):
    base = dict(schema_version=SCHEMA_VERSION, tool_version="0.2.0",
                generated_at="2026-06-18T00:00:00-07:00", root_sha256_prefix="abcd",
                root=None, absolute_paths_included=False, repo_count=1, dirty_count=0,
                class_counts={"public": 1}, top_level=(), repositories=(_row(),))
    base.update(over)
    return Map(**base)


def test_map_to_json_portable_omits_root_and_empty_annotations():
    data = _map().to_json()
    assert data["schema_version"] == 1
    assert "root" not in data
    assert "annotations" not in data
    assert data["repositories"][0]["class"] == "public"


def test_map_to_json_local_includes_root_and_annotations():
    data = _map(root="C:/dev", absolute_paths_included=True,
                annotations={"operating_model": "x"}).to_json()
    assert data["root"] == "C:/dev"
    assert data["annotations"] == {"operating_model": "x"}
