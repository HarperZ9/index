from __future__ import annotations

import threading
import io
import json
from pathlib import Path

import pytest

from index_graph.context.pack import to_json
from index_graph.graph.build import build_graph

FIX = Path(__file__).parent / "fixtures"


def test_progress_arrives_before_slowest_repo_and_preserves_output(tmp_path):
    release_first = threading.Event()

    class Resolver:
        name = "controlled"

        def matches(self, root):
            return True

        def exposed_names(self, root):
            return {root.name}

        def raw_edges(self, root):
            if root.name == "a":
                assert release_first.wait(3), "progress waited for input order"
            return []

    paths = {name: tmp_path / name for name in ("a", "b")}
    for path in paths.values():
        path.mkdir()
    events = []

    def observe(event):
        events.append(event)
        if event.completed_repos >= 1:
            release_first.set()

    graph = build_graph(paths, resolvers=[Resolver()], jobs=2,
                        use_cache=False, on_progress=observe)
    assert [node.name for node in graph.repos] == ["a", "b"]
    assert events[0].phase == "building"
    assert events[0].completed_repos == 0
    assert events[-1].phase == "complete"
    assert events[-1].completed_repos == events[-1].total_repos == 2
    assert [event.completed_repos for event in events] == sorted(
        event.completed_repos for event in events
    )
    assert all(event.elapsed_ms >= 0 for event in events)


def test_progress_does_not_change_dependency_evidence():
    paths = {"py-app": FIX / "py-app", "py-lib": FIX / "py-lib"}
    events = []
    expected = to_json(build_graph(paths, jobs=1, use_cache=False))
    actual = to_json(build_graph(paths, jobs=2, use_cache=False,
                                 on_progress=events.append))
    assert actual == expected
    assert events[-2].phase == "resolving"
    assert events[-1].phase == "complete"


def test_failed_graph_never_emits_complete(tmp_path):
    class BrokenResolver:
        name = "broken"

        def matches(self, root):
            raise RuntimeError("source failed")

    events = []
    with pytest.raises(RuntimeError, match="source failed"):
        build_graph({"repo": tmp_path}, resolvers=[BrokenResolver()],
                    use_cache=False, on_progress=events.append)
    assert events[-1].phase == "failed"
    assert events[-1].completed_repos == 0
    assert not any(event.phase == "complete" for event in events)


def test_empty_graph_reports_actual_zero_total():
    events = []
    graph = build_graph({}, use_cache=False, on_progress=events.append)
    assert graph.repos == ()
    assert events[-1].phase == "complete"
    assert events[-1].completed_repos == events[-1].total_repos == 0


def test_failed_worker_cancels_queued_repositories_before_waiting(tmp_path, monkeypatch):
    import index_graph.graph.build as build
    from concurrent.futures import ThreadPoolExecutor

    release = threading.Event()
    shutting_down = threading.Event()
    started = []
    failures = []

    class ObservedPool(ThreadPoolExecutor):
        def __exit__(self, *args):
            shutting_down.set()
            return super().__exit__(*args)

    class Resolver:
        name = "failure-control"
        def matches(self, root):
            started.append(root.name)
            if root.name == "a-fail":
                raise RuntimeError("source failed")
            assert release.wait(5), "test controller did not release active workers"
            return False

    monkeypatch.setattr(build, "ThreadPoolExecutor", ObservedPool)
    paths = {name: tmp_path / name for name in ("a-fail", *[f"repo-{i}" for i in range(10)])}
    for path in paths.values():
        path.mkdir()

    def run():
        try:
            build_graph(paths, resolvers=[Resolver()], jobs=2, use_cache=False)
        except RuntimeError as exc:
            failures.append(str(exc))

    controller = threading.Thread(target=run)
    controller.start()
    try:
        assert shutting_down.wait(5), "failure was not observed"
    finally:
        release.set()
        controller.join(5)
    assert not controller.is_alive()
    assert failures == ["source failed"]
    assert len(started) <= 3, "queued scans continued after the graph had already failed"


def test_mcp_router_progress_does_not_corrupt_response(tmp_path, monkeypatch, capsys):
    from index_graph.mcp import serve

    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\n", encoding="utf-8")
    monkeypatch.setenv("INDEX_MCP_CACHE_TTL_SECONDS", "0")
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "index_router", "arguments": {"root": str(tmp_path)}}}
    output = io.StringIO()
    serve(io.StringIO(json.dumps(request) + "\n"), output)
    response = json.loads(output.getvalue())
    assert response["result"]["isError"] is False
    assert "# Workspace map" in response["result"]["content"][0]["text"]
    progress = [json.loads(line) for line in capsys.readouterr().err.splitlines()
                if line.startswith('{"schema": "index.graph-progress/v1"')]
    assert progress
    assert progress[-1]["phase"] == "complete"
    assert "index.graph-progress" not in output.getvalue()


def test_spawn_process_graph_matches_serial_and_reports_in_parent(tmp_path, monkeypatch):
    import os

    monkeypatch.setenv("INDEX_GRAPH_REPO_CACHE_DIR", str(tmp_path / "cache"))
    paths = {"py-app": FIX / "py-app", "py-lib": FIX / "py-lib"}
    parent_pid = os.getpid()
    events = []

    def observe(event):
        assert os.getpid() == parent_pid
        events.append(event)

    expected = to_json(build_graph(paths, jobs=1, use_cache=False))
    actual = to_json(build_graph(paths, jobs=2, use_cache=False,
                                 executor="process", on_progress=observe))
    assert actual == expected
    assert events[-1].phase == "complete"


def test_invalid_executor_is_rejected_before_work(tmp_path):
    with pytest.raises(ValueError, match="executor"):
        build_graph({"repo": tmp_path}, executor="pretend")
