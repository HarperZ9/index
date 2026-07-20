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
