import io
import pytest

from index_graph.graph.build import build_graph


def _cache_files(cache):
    return sorted(cache.glob("*.json"))


def _assert_cached_build_is_reused(repo, cache, monkeypatch):
    import index_graph.graph.build as build

    assert len(_cache_files(cache)) == 1

    def fail_build(*args, **kwargs):
        raise AssertionError("expected repo build to come from the graph cache")

    monkeypatch.setattr(build, "_build_one_repo", fail_build)
    graph = build.build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in graph.edges} == {"alpha"}


def test_cache_miss_hashing_and_python_parser_share_working_bytes(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    source = repo / "main.py"
    source.write_bytes(b"import alpha\r\n")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    original = io.open
    reads = []

    def counted_open(path, *args, **kwargs):
        if str(path) == str(source):
            reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(io, "open", counted_open)
    graph = build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in graph.edges} == {"alpha"}
    assert len(reads) == 1, "fingerprint and parser reopened the same working source"


def test_reused_source_bytes_expire_after_each_build(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    source = repo / "main.py"
    source.write_bytes(b"import alpha\r\n")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    before = build_graph({"sample": repo}, jobs=1)
    source.write_bytes(b"import bravo\r\n")
    after = build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in before.edges} == {"alpha"}
    assert {edge.target_name for edge in after.edges} == {"bravo"}


def test_read_reuse_limit_does_not_reduce_coverage_or_change_newlines(tmp_path, monkeypatch):
    import index_graph.graph.walk as walk

    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_BYTES", 1)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (repo / "main.py").write_bytes(b"# invalid UTF-8 in a comment: \xff\rimport alpha\r\nfrom bravo import thing\n")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    graph = build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in graph.edges} == {"alpha", "bravo"}
    from index_graph.context.pack import to_json
    rows = to_json(graph)["relations"]
    evidence = {row["target_name"]: row["signals"][0]["line"] for row in rows}
    assert evidence == {"alpha": 2, "bravo": 3}


def test_byte_cap_overflow_with_stable_source_can_persist_cache(tmp_path, monkeypatch):
    import index_graph.graph.walk as walk

    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_BYTES", 1)
    cache = tmp_path / "cache"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (repo / "main.py").write_text("import alpha\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(cache))

    graph = build_graph({"sample": repo}, jobs=1)

    assert {edge.target_name for edge in graph.edges} == {"alpha"}
    _assert_cached_build_is_reused(repo, cache, monkeypatch)


def test_file_cap_overflow_with_stable_source_can_persist_cache(tmp_path, monkeypatch):
    import index_graph.graph.walk as walk

    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_BYTES", 1024 * 1024)
    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_FILES", 1)
    cache = tmp_path / "cache"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (repo / "main.py").write_text("import alpha\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(cache))

    graph = build_graph({"sample": repo}, jobs=1)

    assert {edge.target_name for edge in graph.edges} == {"alpha"}
    _assert_cached_build_is_reused(repo, cache, monkeypatch)


def test_digest_journal_limit_disables_cache_but_not_coverage(tmp_path, monkeypatch):
    import index_graph.graph.walk as walk

    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_BYTES", 0)
    monkeypatch.setattr(walk, "_SOURCE_DIGEST_JOURNAL_MAX_ENTRIES", 1)
    cache = tmp_path / "cache"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (repo / "main.py").write_text("import alpha\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(cache))

    graph = build_graph({"sample": repo}, jobs=1)

    assert {edge.target_name for edge in graph.edges} == {"alpha"}
    assert _cache_files(cache) == []


@pytest.mark.parametrize("limit", ["_SOURCE_CACHE_MAX_BYTES", "_SOURCE_CACHE_MAX_FILES"])
def test_uncached_source_churn_never_poisons_earlier_fingerprint(tmp_path, monkeypatch, limit):
    import index_graph.graph.walk as walk
    import index_graph.graph.build as build

    monkeypatch.setattr(walk, limit, 0)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    source = repo / "main.py"
    source.write_text("import alpha\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    original = build.make_lookup

    def changed_after_fingerprint(*args, **kwargs):
        lookup = original(*args, **kwargs)
        source.write_text("import bravo\n", encoding="utf-8")
        return lookup

    monkeypatch.setattr(build, "make_lookup", changed_after_fingerprint)
    churned = build.build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in churned.edges} == {"bravo"}
    assert _cache_files(tmp_path / "cache") == []
    source.write_text("import alpha\n", encoding="utf-8")
    monkeypatch.setattr(build, "make_lookup", original)
    after = build.build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in after.edges} == {"alpha"}
    assert len(_cache_files(tmp_path / "cache")) == 1


def test_journaled_source_shrinking_into_byte_cache_cannot_poison_fingerprint(tmp_path, monkeypatch):
    import index_graph.graph.walk as walk
    import index_graph.graph.build as build

    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_BYTES", 64)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    source = repo / "main.py"
    alpha = "import alpha\n# " + "padding" * 30 + "\n"
    source.write_text(alpha, encoding="utf-8")
    cache = tmp_path / "cache"
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(cache))
    original = build.make_lookup

    def shrink_after_fingerprint(*args, **kwargs):
        lookup = original(*args, **kwargs)
        source.write_text("import bravo\n", encoding="utf-8")
        return lookup

    monkeypatch.setattr(build, "make_lookup", shrink_after_fingerprint)
    churned = build.build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in churned.edges} == {"bravo"}
    assert _cache_files(cache) == []
    source.write_text(alpha, encoding="utf-8")
    monkeypatch.setattr(build, "make_lookup", original)
    stable = build.build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in stable.edges} == {"alpha"}
    assert len(_cache_files(cache)) == 1


@pytest.mark.parametrize("name,alpha,bravo", [
    ("package.json", '{"name":"sample","dependencies":{"alpha":"1"}}',
     '{"name":"sample","dependencies":{"bravo":"1"}}'),
    ("pyproject.toml", '[project]\nname="sample"\ndependencies=["alpha"]\n',
     '[project]\nname="sample"\ndependencies=["bravo"]\n'),
])
def test_above_cap_manifest_churn_disables_cache_until_source_is_stable(
    tmp_path, monkeypatch, name, alpha, bravo
):
    import index_graph.graph.walk as walk
    import index_graph.graph.build as build

    monkeypatch.setattr(walk, "_SOURCE_CACHE_MAX_BYTES", 0)
    cache = tmp_path / "cache"
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest = repo / name
    manifest.write_text(alpha, encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(cache))
    original = build.make_lookup

    def changed_after_fingerprint(*args, **kwargs):
        lookup = original(*args, **kwargs)
        manifest.write_text(bravo, encoding="utf-8")
        return lookup

    monkeypatch.setattr(build, "make_lookup", changed_after_fingerprint)
    churned = build.build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in churned.edges} == {"bravo"}
    assert _cache_files(cache) == []

    manifest.write_text(alpha, encoding="utf-8")
    monkeypatch.setattr(build, "make_lookup", original)
    stable = build.build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in stable.edges} == {"alpha"}
    assert len(_cache_files(cache)) == 1


@pytest.mark.parametrize("name,alpha,bravo", [
    ("package.json", '{"name":"sample","dependencies":{"alpha":"1"}}',
     '{"name":"sample","dependencies":{"bravo":"1"}}'),
    ("pyproject.toml", '[project]\nname="sample"\ndependencies=["alpha"]\n',
     '[project]\nname="sample"\ndependencies=["bravo"]\n'),
])
def test_manifest_parser_uses_the_same_bytes_as_its_fingerprint(tmp_path, monkeypatch, name, alpha, bravo):
    import index_graph.graph.build as build

    repo = tmp_path / "repo"
    repo.mkdir()
    manifest = repo / name
    manifest.write_text(alpha, encoding="utf-8")
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    original = build.make_lookup

    def changed_after_fingerprint(*args, **kwargs):
        lookup = original(*args, **kwargs)
        manifest.write_text(bravo, encoding="utf-8")
        return lookup

    monkeypatch.setattr(build, "make_lookup", changed_after_fingerprint)
    graph = build.build_graph({"sample": repo}, jobs=1)
    assert {edge.target_name for edge in graph.edges} == {"alpha"}


def test_linked_repository_uses_one_source_coordinate_frame(tmp_path, monkeypatch):
    repo = tmp_path / "physical"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (repo / "main.py").write_text("import alpha\n", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(repo, target_is_directory=True)
    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    first = build_graph({"sample": alias}, jobs=1)
    assert {edge.target_name for edge in first.edges} == {"alpha"}
    assert first.repos[0].path == str(alias)
    # A cache entry shared by equivalent roots must not preserve another
    # caller's path spelling in the public node metadata.
    direct = build_graph({"sample": repo}, jobs=1)
    assert direct.repos[0].path == str(repo)
    assert {edge.target_name for edge in direct.edges} == {"alpha"}
