from index_graph.model import Map, RepoRow, SCHEMA_VERSION


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
    assert data["metadata_status"] == "ok"


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
    assert data["dirty_count_status"] == "complete"
    assert data["metadata_status"] == "ok"
    assert data["metadata_ok_count"] == 1
    assert data["metadata_unknown_count"] == 0


def test_map_to_json_local_includes_root_and_annotations():
    data = _map(root="C:/workspace", absolute_paths_included=True,
                annotations={"operating_model": "x"}).to_json()
    assert data["root"] == "C:/workspace"
    assert data["annotations"] == {"operating_model": "x"}


def test_map_to_json_marks_dirty_count_known_only_with_unknown_metadata():
    unknown = _row(metadata_status="unknown", metadata_error="GitMetadataError")
    data = _map(repositories=(unknown,)).to_json()

    assert data["dirty_count"] == 0
    assert data["dirty_count_status"] == "known_only"
    assert data["metadata_status"] == "partial"
    assert data["metadata_ok_count"] == 0
    assert data["metadata_unknown_count"] == 1
    assert data["repositories"][0]["metadata_error"] == "GitMetadataError"
