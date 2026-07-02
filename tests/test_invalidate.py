"""Tests for the typed invalidation report (index.invalidation/1).

The staleness contract: a freshness verdict says THAT the workspace moved;
the invalidation report says WHAT that movement invalidates, with a reason
code from a closed set, and its counts must reconcile (invalidated +
still_valid == fingerprinted scope). A report that cannot fail on a
known-bad input would not be a check, so the tampered fixtures here MUST
turn the verdict or the reconciliation.
"""
import json

import pytest

from index_graph.cli import main
from index_graph.freshness.invalidate import (
    ARTIFACTS,
    PIN_SCHEMA,
    REASON_CODES,
    REPORT_SCHEMA,
    invalidation_report,
    mint_pin,
    reconcile_invalidation,
)
from index_graph.mcp import handle_request


def _repo(d, name, dep=None):
    (d / ".git").mkdir(parents=True)
    deps = f'["{dep}"]' if dep else "[]"
    (d / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\ndependencies = {deps}\n',
        encoding="utf-8",
    )
    (d / "main.py").write_text((f"import {dep}\n") if dep else "x = 1\n", encoding="utf-8")
    (d / "README.md").write_text(f"# {name}\n\n{name} does one thing.\n", encoding="utf-8")
    return d


def _workspace(tmp_path):
    _repo(tmp_path / "app", "app", dep="lib")
    _repo(tmp_path / "lib", "lib")
    return tmp_path


def _by_scope(report):
    return {item["artifact_or_scope"]: item for item in report["invalidated"]}


# --- the closed reason-code set ---


def test_reason_codes_are_the_closed_set():
    assert REASON_CODES == frozenset({
        "file-changed", "file-removed", "dependency-edge-changed",
        "doc-changed", "unversioned",
    })


def test_fingerprinted_artifacts_are_the_stated_scope():
    assert set(ARTIFACTS) == {"certificate", "context-pack", "graph-snapshot"}


# --- the pin ---


def test_pin_shape(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    assert pin["schema"] == PIN_SCHEMA
    assert isinstance(pin["pinned_ref"], str) and len(pin["pinned_ref"]) == 64
    assert set(pin["repos"]) == {"app", "lib"}
    for entry in pin["repos"].values():
        assert entry["graph_files"], "a pin must carry per-file hashes"
        for sha in entry["graph_files"].values():
            assert len(sha) == 64
        assert "README.md" in entry["doc_files"]
    assert pin["snapshot"]["schema"] == "index.snapshot/1"
    assert "app -> lib" in pin["snapshot"]["edges"]


# --- the report: FRESH, and every flavor of STALE ---


def test_report_fresh_when_nothing_moved(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    report = invalidation_report(pin, root)
    assert report["schema"] == REPORT_SCHEMA
    assert report["verdict"] == "FRESH"
    assert report["invalidated"] == []
    assert set(report["still_valid"]) == {
        "certificate", "context-pack", "graph-snapshot", "repo:app", "repo:lib"}
    assert report["pinned_ref"] == report["current_ref"] == pin["pinned_ref"]
    assert report["counts"] == {"scope": 5, "invalidated": 0, "still_valid": 5}


def test_doc_edit_invalidates_pack_and_certificate_but_not_snapshot(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    (root / "app" / "README.md").write_text("# app\n\nrewritten prose.\n", encoding="utf-8")
    report = invalidation_report(pin, root)
    assert report["verdict"] == "STALE"
    scoped = _by_scope(report)
    assert scoped["repo:app"]["reason_code"] == "doc-changed"
    assert scoped["context-pack"]["reason_code"] == "doc-changed"
    assert scoped["certificate"]["reason_code"] == "doc-changed"
    # the diff names what a doc edit does NOT invalidate: the structural snapshot
    assert "graph-snapshot" in report["still_valid"]
    assert "repo:lib" in report["still_valid"]


def test_dependency_rewire_names_dependency_edge_changed(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    (root / "app" / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8")
    (root / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    report = invalidation_report(pin, root)
    assert report["verdict"] == "STALE"
    scoped = _by_scope(report)
    assert scoped["graph-snapshot"]["reason_code"] == "dependency-edge-changed"
    assert any("app -> lib" in e for e in scoped["graph-snapshot"]["evidence"])
    assert scoped["repo:app"]["reason_code"] == "file-changed"
    assert "certificate" in scoped and "context-pack" in scoped
    assert "repo:lib" in report["still_valid"]


def test_removed_source_file_names_file_removed(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    (root / "app" / "main.py").unlink()
    report = invalidation_report(pin, root)
    assert report["verdict"] == "STALE"
    scoped = _by_scope(report)
    assert scoped["repo:app"]["reason_code"] == "file-removed"
    assert "main.py" in " ".join(scoped["repo:app"]["evidence"])
    assert scoped["certificate"]["reason_code"] == "file-removed"


def test_new_repo_is_unversioned(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    _repo(root / "newcomer", "newcomer")
    report = invalidation_report(pin, root)
    assert report["verdict"] == "STALE"
    scoped = _by_scope(report)
    assert scoped["graph-snapshot"]["reason_code"] == "unversioned"
    assert any("newcomer" in e for e in scoped["graph-snapshot"]["evidence"])
    # the pinned repo scopes themselves did not move
    assert "repo:app" in report["still_valid"]
    assert "repo:lib" in report["still_valid"]


def test_tampered_pin_yields_stale_file_changed_not_a_crash(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    victim = sorted(pin["repos"]["app"]["graph_files"])[0]
    pin["repos"]["app"]["graph_files"][victim] = "a" * 64
    report = invalidation_report(pin, root)
    assert report["verdict"] == "STALE"
    assert _by_scope(report)["repo:app"]["reason_code"] == "file-changed"


def test_counts_reconcile_on_every_report(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    (root / "app" / "README.md").write_text("# moved\n", encoding="utf-8")
    (root / "lib" / "main.py").write_text("y = 2\n", encoding="utf-8")
    report = invalidation_report(pin, root)
    counts = report["counts"]
    assert counts["invalidated"] + counts["still_valid"] == counts["scope"]
    assert counts["invalidated"] == len(report["invalidated"])
    assert counts["still_valid"] == len(report["still_valid"])
    assert reconcile_invalidation(report)["verdict"] == "MATCH"


def test_non_pin_document_is_a_value_error(tmp_path):
    root = _workspace(tmp_path)
    with pytest.raises(ValueError):
        invalidation_report({"schema": "nope"}, root)


# --- negative fixtures: the reconciliation MUST reject known-bad reports ---


def test_reconcile_rejects_forged_counts(tmp_path):
    root = _workspace(tmp_path)
    report = invalidation_report(mint_pin(root), root)
    report["counts"]["still_valid"] += 1
    verdict = reconcile_invalidation(report)
    assert verdict["verdict"] == "DRIFT"
    codes = {f["code"] for f in verdict["failures"]}
    assert codes & {"counts-mismatch", "still-valid-count-mismatch"}


def test_reconcile_rejects_unknown_reason_code(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    (root / "app" / "README.md").write_text("# moved\n", encoding="utf-8")
    report = invalidation_report(pin, root)
    report["invalidated"][0]["reason_code"] = "vibes"
    verdict = reconcile_invalidation(report)
    assert verdict["verdict"] == "DRIFT"
    assert "unknown-reason-code" in {f["code"] for f in verdict["failures"]}


def test_reconcile_rejects_fresh_verdict_over_invalidations(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    (root / "app" / "README.md").write_text("# moved\n", encoding="utf-8")
    report = invalidation_report(pin, root)
    report["verdict"] = "FRESH"
    verdict = reconcile_invalidation(report)
    assert verdict["verdict"] == "DRIFT"
    assert "verdict-mismatch" in {f["code"] for f in verdict["failures"]}


def test_reconcile_rejects_double_booked_scope(tmp_path):
    root = _workspace(tmp_path)
    pin = mint_pin(root)
    (root / "app" / "README.md").write_text("# moved\n", encoding="utf-8")
    report = invalidation_report(pin, root)
    report["still_valid"].append(report["invalidated"][0]["artifact_or_scope"])
    report["counts"]["still_valid"] += 1
    report["counts"]["scope"] += 1
    verdict = reconcile_invalidation(report)
    assert verdict["verdict"] == "DRIFT"
    assert "duplicate-scope" in {f["code"] for f in verdict["failures"]}


# --- CLI face ---


def test_cli_mint_then_report_fresh_then_stale(tmp_path, capsys):
    root = _workspace(tmp_path)
    pin_file = tmp_path / "pin.json"
    rc = main(["invalidate", "--root", str(root), "--out", str(pin_file)])
    assert rc == 0
    assert json.loads(pin_file.read_text(encoding="utf-8"))["schema"] == PIN_SCHEMA
    capsys.readouterr()

    rc = main(["invalidate", "--root", str(root), "--pin", str(pin_file), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report"]["verdict"] == "FRESH"
    assert payload["reconciliation"]["verdict"] == "MATCH"

    (root / "app" / "README.md").write_text("# moved\n", encoding="utf-8")
    rc = main(["invalidate", "--root", str(root), "--pin", str(pin_file)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "STALE" in out and "doc-changed" in out


def test_cli_non_pin_document_is_unverifiable_not_a_crash(tmp_path, capsys):
    root = _workspace(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "not-a-pin"}), encoding="utf-8")
    rc = main(["invalidate", "--root", str(root), "--pin", str(bad), "--json"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["report"]["verdict"] == "UNVERIFIABLE"


def test_cli_requires_exactly_one_of_out_or_pin(tmp_path):
    root = _workspace(tmp_path)
    with pytest.raises(SystemExit):
        main(["invalidate", "--root", str(root)])
    with pytest.raises(SystemExit):
        main(["invalidate", "--root", str(root),
              "--out", str(tmp_path / "a.json"), "--pin", str(tmp_path / "b.json")])


# --- MCP parity ---


def test_mcp_invalidate_mints_and_reports(tmp_path):
    root = _workspace(tmp_path)
    minted = handle_request({"jsonrpc": "2.0", "id": 20, "method": "tools/call",
                             "params": {"name": "index.invalidate",
                                        "arguments": {"root": str(root)}}})
    assert minted["result"]["isError"] is False
    pin = json.loads(minted["result"]["content"][0]["text"])
    assert pin["schema"] == PIN_SCHEMA

    pin_file = tmp_path / "pin.json"
    pin_file.write_text(json.dumps(pin), encoding="utf-8")
    (root / "app" / "README.md").write_text("# moved\n", encoding="utf-8")
    reported = handle_request({"jsonrpc": "2.0", "id": 21, "method": "tools/call",
                               "params": {"name": "index.invalidate",
                                          "arguments": {"root": str(root),
                                                        "pin": str(pin_file)}}})
    assert reported["result"]["isError"] is False
    payload = json.loads(reported["result"]["content"][0]["text"])
    assert payload["report"]["verdict"] == "STALE"
    assert payload["reconciliation"]["verdict"] == "MATCH"


def test_status_advertises_invalidate_surface():
    from index_graph.flagship import status_payload
    native = status_payload()["native"]
    assert "invalidate" in native["commands"]
    assert "index.invalidate" in native["mcp_tools"]
    listed = handle_request({"jsonrpc": "2.0", "id": 22, "method": "tools/list"})
    assert "index.invalidate" in {t["name"] for t in listed["result"]["tools"]}
