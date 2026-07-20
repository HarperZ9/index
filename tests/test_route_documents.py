import pytest

from index_graph.route.budget import WorkBudget
from index_graph.route.documents import select_documents
from index_graph.route.reads import DocumentReader
from index_graph.route.scope import RepoCandidate


def _candidate(root, rel):
    repo = root / rel
    (repo / ".git").mkdir(parents=True)
    return RepoCandidate(rel, repo, rel, "explicit")


def test_max_docs_caps_bodies_opened(tmp_path):
    candidate = _candidate(tmp_path, "public/index")
    for number in range(20):
        (candidate.path / f"doc-{number:02}.md").write_text(
            f"# Doc {number}\nbody\n", encoding="utf-8"
        )
    budget = WorkBudget.start(5000)
    result = select_documents(tmp_path, [candidate], "", 8, budget)
    assert len(result.docs) == 8
    assert budget.counters["document_bodies_opened"] == 8
    assert len(result.omitted) == 12
    assert {item["reason_code"] for item in result.omitted} == {"max-docs"}


def test_document_walk_never_visits_unselected_sibling(tmp_path):
    selected = _candidate(tmp_path, "public/index")
    sibling = _candidate(tmp_path, "public/forum")
    (selected.path / "README.md").write_text("# Index\n", encoding="utf-8")
    (sibling.path / "SECRET.md").write_text("# Must not be read\n", encoding="utf-8")
    result = select_documents(tmp_path, [selected], "index", 8, WorkBudget.start(5000))
    assert [doc.rel_path for doc in result.docs] == ["public/index/README.md"]


def test_budget_expiration_omits_remaining_documents(tmp_path):
    candidate = _candidate(tmp_path, "public/index")
    for number in range(5):
        (candidate.path / f"{number}.md").write_text("# D\n", encoding="utf-8")
    ticks = iter((0.0, 0.0, 0.003, 0.006, 0.006, 0.006, 0.006))
    budget = WorkBudget.start(5, clock=lambda: next(ticks, 0.006))
    result = select_documents(tmp_path, [candidate], "", 8, budget)
    assert result.complete is False
    assert any(item["reason_code"] == "budget-exhausted" for item in result.omitted)


def test_supplied_reader_requires_matching_root(tmp_path):
    budget = WorkBudget.start(5000)
    reader = DocumentReader(tmp_path, 1, budget)
    with pytest.raises(ValueError, match="reader root"):
        select_documents(tmp_path / "other", [], "", 1, budget, reader=reader)


def test_supplied_reader_requires_matching_max_docs(tmp_path):
    budget = WorkBudget.start(5000)
    reader = DocumentReader(tmp_path, 2, budget)
    with pytest.raises(ValueError, match="reader max_docs"):
        select_documents(tmp_path, [], "", 1, budget, reader=reader)


def test_supplied_reader_requires_matching_budget(tmp_path):
    reader = DocumentReader(tmp_path, 1, WorkBudget.start(5000))
    with pytest.raises(ValueError, match="reader budget"):
        select_documents(tmp_path, [], "", 1, WorkBudget.start(5000), reader=reader)


def test_max_docs_is_validated_with_supplied_reader(tmp_path):
    budget = WorkBudget.start(5000)
    reader = DocumentReader(tmp_path, 1, budget)
    with pytest.raises(ValueError, match="max_docs must be >= 0"):
        select_documents(tmp_path, [], "", -1, budget, reader=reader)


def test_matching_reader_reuses_cached_body_at_the_cap(tmp_path):
    candidate = _candidate(tmp_path, "public/index")
    readme = candidate.path / "README.md"
    readme.write_text("# Index\n", encoding="utf-8")
    budget = WorkBudget.start(5000)
    reader = DocumentReader(tmp_path, 1, budget)
    assert reader.read(readme) == "# Index\n"

    result = select_documents(tmp_path, [candidate], "", 1, budget, reader=reader)

    assert [doc.rel_path for doc in result.docs] == ["public/index/README.md"]
    assert budget.counters["document_bodies_opened"] == 1


def test_overlapping_repositories_book_each_document_once(tmp_path):
    parent = _candidate(tmp_path, "public/index")
    nested = _candidate(tmp_path, "public/index/nested")
    (nested.path / "README.md").write_text("# Nested\n", encoding="utf-8")
    budget = WorkBudget.start(5000)

    result = select_documents(tmp_path, [parent, nested], "", 8, budget)

    assert [doc.rel_path for doc in result.docs] == ["public/index/nested/README.md"]
    assert result.candidates == ("public/index/nested/README.md",)
    assert budget.counters["candidate_documents_observed"] == 1
    assert result.reconciliation["verdict"] == "MATCH"
