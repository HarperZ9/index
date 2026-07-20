from index_graph.config import default_config
from index_graph.freshness.fingerprint import relevant_files
from index_graph.graph.build import build_graph
from index_graph.graph.walk import walk_budget, walk_files
from index_graph.scan import discover_repos


def _tree(root):
    for index in range(6):
        repo = root / f"repo-{index}"
        (repo / ".git").mkdir(parents=True)
        (repo / "src").mkdir()
        (repo / "src" / f"mod{index}.py").write_text("x = 1\n", encoding="utf-8")


def test_discover_repos_checkpoint_stops_new_work(tmp_path):
    _tree(tmp_path)
    calls = []

    def checkpoint(boundary):
        calls.append(boundary)
        return len(calls) < 4

    repos = discover_repos(tmp_path, default_config(), checkpoint=checkpoint)
    assert len(repos) < 6
    assert calls[-1] == "scan.directory"


def test_walk_files_is_exhaustive_without_checkpoint(tmp_path):
    _tree(tmp_path)
    assert len(list(walk_files(tmp_path, suffixes=(".py",)))) == 6


def test_walk_budget_stops_existing_resolver_walk(tmp_path):
    _tree(tmp_path)
    calls = []

    def checkpoint(boundary):
        calls.append(boundary)
        return len(calls) < 3

    with walk_budget(checkpoint):
        found = list(walk_files(tmp_path, suffixes=(".py",)))
    assert len(found) < 6
    assert "graph.walk.directory" in calls


def test_relevant_files_checkpoint_and_default_compatibility(tmp_path):
    _tree(tmp_path)
    assert len(list(relevant_files(tmp_path))) == 6
    calls = []
    bounded = list(
        relevant_files(
            tmp_path,
            checkpoint=lambda boundary: calls.append(boundary) is None and len(calls) < 3,
        )
    )
    assert len(bounded) < 6


def test_build_graph_marks_budget_exhaustion(tmp_path):
    _tree(tmp_path)
    calls = []

    def checkpoint(boundary):
        calls.append(boundary)
        return boundary != "graph.repo"

    graph = build_graph(
        {f"repo-{i}": tmp_path / f"repo-{i}" for i in range(6)},
        checkpoint=checkpoint,
    )
    assert graph.warnings[-1] == "budget-exhausted:graph.repo"
    assert calls == ["graph.repo"]


def test_build_graph_uses_supplied_document_reader(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    readme = repo / "README.md"
    readme.write_text("# Repo\n\nExpected description.\n", encoding="utf-8")
    seen = []

    def reader(path):
        seen.append(path)
        return path.read_text(encoding="utf-8")

    graph = build_graph({"repo": repo}, document_reader=reader)
    assert readme in seen
    assert graph.repos[0].description == "Expected description."


def test_build_graph_caps_non_markdown_readme_with_supplied_reader(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    readme = repo / "README.rst"
    readme.write_text("# Repo\n\nUncapped source description.\n", encoding="utf-8")
    seen = []

    def reader(path):
        seen.append(path)
        return "# Repo\n\nCapped reader description.\n"

    graph = build_graph({"repo": repo}, resolvers=(), document_reader=reader)
    assert seen == [readme]
    assert graph.repos[0].description == "Capped reader description."


def test_build_graph_reports_exact_nested_walk_exhaustion(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module.py").write_text("x = 1\n", encoding="utf-8")

    class WalkingResolver:
        name = "walking"

        def matches(self, root):
            return any(walk_files(root, suffixes=(".py",)))

        def exposed_names(self, root):
            return set()

        def raw_edges(self, root):
            return []

    graph = build_graph(
        {"repo": repo},
        resolvers=(WalkingResolver(),),
        checkpoint=lambda boundary: boundary != "graph.walk.directory",
    )
    assert graph.warnings[-1] == "budget-exhausted:graph.walk.directory"


def test_build_graph_omits_roles_for_unvisited_repositories(tmp_path):
    repos = {name: tmp_path / name for name in ("first", "second")}
    for repo in repos.values():
        repo.mkdir()
    repo_calls = 0

    def checkpoint(boundary):
        nonlocal repo_calls
        if boundary == "graph.repo":
            repo_calls += 1
            return repo_calls == 1
        return True

    graph = build_graph(repos, resolvers=(), checkpoint=checkpoint)
    assert [repo.name for repo in graph.repos] == ["first"]
    assert set(graph.roles) == {"first"}


def test_walk_files_orders_reverse_created_directories_and_files(tmp_path):
    for dirname in ("zeta", "alpha"):
        directory = tmp_path / dirname
        directory.mkdir()
        for filename in ("z.py", "a.py"):
            (directory / filename).write_text("x = 1\n", encoding="utf-8")

    assert [path.relative_to(tmp_path).as_posix() for path in walk_files(tmp_path, suffixes=(".py",))] == [
        "alpha/a.py",
        "alpha/z.py",
        "zeta/a.py",
        "zeta/z.py",
    ]
