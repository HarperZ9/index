"""Path selection with typed rejection receipts (index.path-selection/v1).

The through-line: a selector that cannot show what it dropped is not
auditable, and a reconciliation check that cannot fail on a tampered
selection is not a check. Half of these tests are negative fixtures.
"""
from __future__ import annotations

import json

import pytest

from index_graph.cli import main
from index_graph.context.select import (
    REASON_CODES,
    RECEIPT_SCHEMA,
    RECONCILIATION_SCHEMA,
    RESULT_SCHEMA,
    probe_readable,
    reconcile_selection,
    reject_selected,
    select_paths,
    validate_receipt,
)


def _workspace(root):
    (root / "pkg").mkdir()
    (root / "pkg" / "a.md").write_text("# a\n", encoding="utf-8")
    (root / "pkg" / "b.py").write_text("x = 1\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "dep.md").write_text("# buried\n", encoding="utf-8")
    (root / "README.md").write_text("# top\n", encoding="utf-8")


# --- positive path: selected + rejected reconcile, receipts are typed ---


def test_select_splits_every_candidate_into_selected_or_rejected(tmp_path):
    _workspace(tmp_path)

    selection = select_paths(tmp_path, suffixes=(".md",))

    assert selection["schema"] == RESULT_SCHEMA
    assert selection["selected"] == ["README.md", "pkg/a.md"]
    rejected = {item["path"]: item for item in selection["rejected"]}
    assert rejected["pkg/b.py"]["reason_code"] == "suffix-mismatch"
    assert rejected["node_modules"]["reason_code"] == "excluded-by-rule"
    assert "EXCLUDE_DIRS" in rejected["node_modules"]["rule_ref"]
    # the buried file never bypasses the pruned dir's receipt
    assert "node_modules/dep.md" not in rejected
    counts = selection["counts"]
    assert counts["candidates"] == counts["selected"] + counts["rejected"]
    assert counts["selected"] == 2
    for receipt in selection["rejected"]:
        assert receipt["schema"] == RECEIPT_SCHEMA == "index.path-selection/v1"
        assert validate_receipt(receipt) == []
    assert reconcile_selection(selection)["verdict"] == "MATCH"


def test_select_over_budget_yields_receipts_not_silence(tmp_path):
    for name in ("a.md", "b.md", "c.md"):
        (tmp_path / name).write_text("# doc\n", encoding="utf-8")

    selection = select_paths(tmp_path, suffixes=(".md",), max_files=1)

    assert selection["counts"]["selected"] == 1
    over = [r for r in selection["rejected"] if r["reason_code"] == "over-budget"]
    assert len(over) == 2
    assert all(r["rule_ref"] == "select.max_files:1" for r in over)
    assert selection["counts"]["candidates"] == 3
    assert reconcile_selection(selection)["verdict"] == "MATCH"


def test_select_missing_root_is_a_not_found_receipt(tmp_path):
    selection = select_paths(tmp_path / "does-not-exist")

    assert selection["selected"] == []
    assert [r["reason_code"] for r in selection["rejected"]] == ["not-found"]
    assert selection["counts"] == {"candidates": 1, "selected": 0, "rejected": 1}
    assert reconcile_selection(selection)["verdict"] == "MATCH"


def test_probe_readable_moves_unreadable_files_to_rejected(tmp_path, monkeypatch):
    _workspace(tmp_path)
    selection = select_paths(tmp_path, suffixes=(".md",))

    import index_graph.context.select as select_mod

    def _fail_on_a(path):
        if path.name == "a.md":
            raise OSError("permission denied")

    monkeypatch.setattr(select_mod, "_read_probe", _fail_on_a)
    probed = probe_readable(selection, tmp_path)

    assert "pkg/a.md" not in probed["selected"]
    receipt = next(r for r in probed["rejected"] if r["path"] == "pkg/a.md")
    assert receipt["reason_code"] == "unreadable"
    assert receipt["rule_ref"] == "select.read_check"
    assert probed["counts"]["candidates"] == selection["counts"]["candidates"]
    assert reconcile_selection(probed)["verdict"] == "MATCH"


# --- negative fixtures: the checks must reject known-bad input ---


def test_validator_rejects_unknown_reason_code():
    receipt = {"schema": RECEIPT_SCHEMA, "path": "pkg/a.md",
               "reason_code": "vibes", "rule_ref": "select.suffixes:.md"}

    errors = validate_receipt(receipt)

    assert any("unknown reason_code" in e for e in errors)
    assert "vibes" not in REASON_CODES


def test_validator_rejects_wrong_schema_missing_and_extra_fields():
    assert validate_receipt("not a receipt")
    assert any("schema" in e for e in validate_receipt(
        {"schema": "index.other/v9", "path": "p", "reason_code": "not-found",
         "rule_ref": "select.root"}))
    assert any("rule_ref" in e for e in validate_receipt(
        {"schema": RECEIPT_SCHEMA, "path": "p", "reason_code": "not-found"}))
    assert any("unknown fields" in e for e in validate_receipt(
        {"schema": RECEIPT_SCHEMA, "path": "p", "reason_code": "not-found",
         "rule_ref": "select.root", "note": "author-controlled"}))


def test_reconcile_rejects_counts_that_do_not_add_up(tmp_path):
    _workspace(tmp_path)
    selection = select_paths(tmp_path, suffixes=(".md",))
    selection["counts"]["candidates"] += 1

    report = reconcile_selection(selection)

    assert report["schema"] == RECONCILIATION_SCHEMA
    assert report["verdict"] == "DRIFT"
    assert any(f["code"] == "counts-mismatch" for f in report["failures"])


def test_reconcile_detects_a_silently_dropped_path(tmp_path):
    _workspace(tmp_path)
    selection = select_paths(tmp_path, suffixes=(".md",))
    # simulate a selector that drops a path without leaving a receipt
    selection["rejected"] = selection["rejected"][1:]

    report = reconcile_selection(selection)

    assert report["verdict"] == "DRIFT"
    assert any(f["code"] == "rejected-count-mismatch" for f in report["failures"])


def test_reconcile_rejects_a_receipt_with_an_unknown_reason_code(tmp_path):
    _workspace(tmp_path)
    selection = select_paths(tmp_path, suffixes=(".md",))
    selection["rejected"][0]["reason_code"] = "trust-me"

    report = reconcile_selection(selection)

    assert report["verdict"] == "DRIFT"
    assert any(f["code"] == "invalid-receipt" for f in report["failures"])


def test_reconcile_rejects_a_double_booked_path(tmp_path):
    _workspace(tmp_path)
    selection = select_paths(tmp_path, suffixes=(".md",))
    # book a selected path as rejected too, keeping declared counts consistent
    selection["rejected"].append({
        "schema": RECEIPT_SCHEMA, "path": selection["selected"][0],
        "reason_code": "over-budget", "rule_ref": "select.max_files:1"})
    selection["counts"]["rejected"] += 1
    selection["counts"]["candidates"] += 1

    report = reconcile_selection(selection)

    assert report["verdict"] == "DRIFT"
    assert any(f["code"] == "duplicate-path" for f in report["failures"])


def test_reject_selected_refuses_unknown_codes_and_unknown_paths(tmp_path):
    _workspace(tmp_path)
    selection = select_paths(tmp_path, suffixes=(".md",))

    with pytest.raises(ValueError, match="unknown reason_code"):
        reject_selected(selection, "pkg/a.md", "vibes", "select.read_check")
    with pytest.raises(ValueError, match="not selected"):
        reject_selected(selection, "ghost.md", "unreadable", "select.read_check")


# --- CLI surface ---


def test_select_cli_json_emits_selection_and_reconciliation(tmp_path, capsys):
    _workspace(tmp_path)

    assert main(["select", "--root", str(tmp_path), "--suffix", ".md",
                 "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["selection"]["schema"] == RESULT_SCHEMA
    assert payload["selection"]["selected"] == ["README.md", "pkg/a.md"]
    assert payload["reconciliation"]["verdict"] == "MATCH"
    assert payload["reconciliation"]["failures"] == []


def test_select_cli_text_summarizes_reason_codes(tmp_path, capsys):
    _workspace(tmp_path)

    assert main(["select", "--root", str(tmp_path), "--suffix", ".md"]) == 0
    out = capsys.readouterr().out

    assert "verdict=MATCH" in out
    assert "excluded-by-rule" in out
    assert "suffix-mismatch" in out
