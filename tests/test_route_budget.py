from pathlib import Path, PurePosixPath

import pytest

import index_graph.route.model as route_model
from index_graph.route.budget import WorkBudget
from index_graph.route import FRESHNESS_MODES, REASON_CODES, VERDICTS
from index_graph.route.model import RouteRequest, reconcile_route, route_item
from index_graph.route.reads import DocumentReader


def test_route_request_defaults_and_normalization(tmp_path):
    request = RouteRequest.create(
        tmp_path,
        query="  repair index  ",
        paths=["public\\index", "public/index"],
    )
    assert request.root == tmp_path.resolve()
    assert request.query == "repair index"
    assert request.paths == ("public/index",)
    assert request.max_repos == 12
    assert request.max_docs == 8
    assert request.budget_ms == 5000
    assert request.freshness == "bounded"


def test_route_request_resolves_paths_to_root_relative_posix_and_deduplicates(tmp_path):
    nested = tmp_path / "public" / "index"
    nested.mkdir(parents=True)
    request = RouteRequest.create(
        tmp_path,
        paths=[
            nested,
            "public/./index",
            "public\\index",
            "public/other/..",
        ],
    )
    assert request.paths == ("public/index", "public")


@pytest.mark.parametrize("path", ["../outside", Path("../outside").resolve()])
def test_route_request_rejects_paths_resolved_outside_root(tmp_path, path):
    with pytest.raises(ValueError, match="outside-root"):
        RouteRequest.create(tmp_path, paths=[path])


def test_route_request_parses_windows_spelling_with_simulated_posix_host(monkeypatch):
    class SimulatedPosixPath(PurePosixPath):
        def resolve(self):
            return self

    monkeypatch.setattr(route_model, "Path", SimulatedPosixPath)
    request = RouteRequest.create(
        "/workspace",
        paths=[r"docs\README.md", "docs/README.md"],
    )
    assert request.paths == ("docs/README.md",)
    with pytest.raises(ValueError, match="outside-root"):
        RouteRequest.create("/workspace", paths=[r"C:\foreign\README.md"])


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_repos", -1), ("max_docs", -1), ("budget_ms", 0), ("freshness", "eventual")],
)
def test_route_request_rejects_invalid_controls(tmp_path, field, value):
    kwargs = {field: value}
    with pytest.raises(ValueError, match=field):
        RouteRequest.create(tmp_path, **kwargs)


def test_work_budget_records_first_exhaustion_boundary():
    ticks = iter((10.000, 10.004, 10.006, 10.007))
    budget = WorkBudget.start(5, clock=lambda: next(ticks))
    assert budget.checkpoint("scope.repo", counter="repositories_visited") is True
    assert budget.checkpoint("docs.open", counter="document_bodies_opened") is False
    assert budget.exhausted_at == "docs.open"
    assert budget.checkpoint("graph.repo") is False
    receipt = budget.to_json()
    assert receipt["repositories_visited"] == 1
    assert receipt["document_bodies_opened"] == 0


def test_work_budget_callback_uses_the_supplied_counter():
    budget = WorkBudget.start(5000)
    callback = budget.callback("files_validated")
    assert callback("freshness.file") is True
    assert budget.counters["files_validated"] == 1


def test_work_budget_rejects_negative_checkpoint_amount():
    budget = WorkBudget.start(5000)
    with pytest.raises(ValueError, match="amount"):
        budget.checkpoint("scope.repo", counter="repositories_visited", amount=-1)
    assert budget.counters["repositories_visited"] == 0


def test_route_module_exports_public_route_vocabularies():
    assert FRESHNESS_MODES == frozenset({"bounded", "strict"})
    assert VERDICTS == frozenset({"MATCH", "PARTIAL", "STALE", "UNVERIFIABLE"})
    assert "outside-root" in REASON_CODES


def test_route_item_requires_stable_reason_codes():
    with pytest.raises(ValueError, match="reason_code"):
        route_item("README.md", "ad-hoc", "test")


@pytest.mark.parametrize(
    "path",
    ["/README.md", "C:/README.md", "docs\\README.md", "./README.md", "docs/../README.md"],
)
def test_route_item_rejects_nonportable_path_spellings(path):
    with pytest.raises(ValueError, match="path"):
        route_item(path, "not-found", "test")


def test_route_item_emits_normalized_root_relative_posix_path():
    item = route_item("docs/README.md", "not-found", "test")
    assert item["path"] == "docs/README.md"


def test_route_reconciliation_detects_no_silent_drop():
    candidates = ["public/index", "public/forum"]
    selected = ["public/index"]
    rejected = []
    omitted = [route_item("public/forum", "max-repos", "route.max_repos:1")]
    report = reconcile_route(candidates, selected, rejected, omitted)
    assert report["verdict"] == "MATCH"
    assert report["counts"] == {
        "candidates": 2,
        "selected": 1,
        "rejected": 0,
        "omitted": 1,
    }


def test_route_reconciliation_reports_unbooked_and_duplicate_candidates():
    unbooked = reconcile_route(["README.md"], [], [], [])
    duplicate = reconcile_route(
        ["README.md"],
        ["README.md"],
        [route_item("README.md", "duplicate", "test")],
        [],
    )
    assert unbooked["verdict"] == "DRIFT"
    assert unbooked["failures"][0]["code"] == "candidate-accounting"
    assert duplicate["verdict"] == "DRIFT"
    assert {failure["code"] for failure in duplicate["failures"]} == {
        "candidate-accounting",
        "duplicate-booking",
    }


def test_document_reader_enforces_global_body_cap_and_reuses_body(tmp_path):
    first = tmp_path / "README.md"
    second = tmp_path / "OTHER.md"
    first.write_text("# Index\n", encoding="utf-8")
    second.write_text("# Other\n", encoding="utf-8")
    budget = WorkBudget.start(5000)
    reader = DocumentReader(tmp_path, 1, budget)
    assert reader.read(first) == "# Index\n"
    assert reader.read(first) == "# Index\n"
    assert reader.read(second) is None
    assert reader.reason(second) == "max-docs"
    assert reader.bodies() == {"README.md": "# Index\n"}
    assert budget.counters["document_bodies_opened"] == 1


def test_document_reader_rejects_outside_root_and_returns_body_copy(tmp_path):
    inside = tmp_path / "README.md"
    outside = tmp_path.parent / "outside.md"
    inside.write_text("inside", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")
    reader = DocumentReader(tmp_path, 1, WorkBudget.start(5000))
    assert reader.read(outside) is None
    assert reader.reason(outside) == "outside-root"
    assert reader.read(inside) == "inside"
    bodies = reader.bodies()
    bodies["README.md"] = "mutated"
    assert reader.bodies() == {"README.md": "inside"}


def test_document_reader_replaces_invalid_utf8_and_reports_missing_file(tmp_path):
    invalid = tmp_path / "invalid.md"
    invalid.write_bytes(b"valid\xfftext")
    missing = tmp_path / "missing.md"
    reader = DocumentReader(tmp_path, 2, WorkBudget.start(5000))
    assert reader.read(invalid) == "valid\ufffdtext"
    assert reader.read(missing) is None
    assert reader.reason(missing) == "not-found"
