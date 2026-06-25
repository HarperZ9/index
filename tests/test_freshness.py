"""Tests for the content fingerprint, the freshness comparison, and the CLI face."""
import json

import pytest

from index_graph.cli import main
from index_graph.freshness import (
    SCHEMA,
    compare_freshness,
    repo_fingerprint,
    workspace_fingerprint,
)


def _py_repo(d, name, dep=None):
    (d / ".git").mkdir(parents=True, exist_ok=True)
    deps = f'["{dep}"]' if dep else "[]"
    (d / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\ndependencies = {deps}\n',
        encoding="utf-8",
    )
    (d / "main.py").write_text(("import %s\n" % dep) if dep else "x = 1\n", encoding="utf-8")
    return d


# --- fingerprint primitive ---


def test_repo_fingerprint_is_deterministic(tmp_path):
    repo = _py_repo(tmp_path / "app", "app")
    assert repo_fingerprint(repo) == repo_fingerprint(repo)


def test_repo_fingerprint_changes_on_source_edit(tmp_path):
    repo = _py_repo(tmp_path / "app", "app")
    before = repo_fingerprint(repo)
    (repo / "main.py").write_text("import os\nx = 2\n", encoding="utf-8")
    assert repo_fingerprint(repo) != before


def test_repo_fingerprint_changes_when_new_ecosystem_manifest_appears(tmp_path):
    """A repo that was Python-only gains a Cargo.toml: the graph could now change,
    so the fingerprint must move even though no Python file was touched."""
    repo = _py_repo(tmp_path / "app", "app")
    before = repo_fingerprint(repo)
    (repo / "Cargo.toml").write_text('[package]\nname = "app"\n', encoding="utf-8")
    assert repo_fingerprint(repo) != before


def test_repo_fingerprint_ignores_irrelevant_files(tmp_path):
    """A README or note edit does not change the graph, so it does not move the
    fingerprint (the fingerprint is scoped to graph-relevant files)."""
    repo = _py_repo(tmp_path / "app", "app")
    before = repo_fingerprint(repo)
    (repo / "README.md").write_text("# app\nlots of prose\n", encoding="utf-8")
    (repo / "notes.txt").write_text("a scratch note\n", encoding="utf-8")
    assert repo_fingerprint(repo) == before


def test_repo_fingerprint_requirements_glob_is_tracked(tmp_path):
    repo = _py_repo(tmp_path / "app", "app")
    before = repo_fingerprint(repo)
    (repo / "requirements-dev.txt").write_text("requests==2.0\n", encoding="utf-8")
    assert repo_fingerprint(repo) != before


def test_repo_fingerprint_fail_closed_on_missing_root(tmp_path):
    # A missing tree yields the empty-set hash, never raises.
    missing = tmp_path / "does-not-exist"
    assert repo_fingerprint(missing) == repo_fingerprint(tmp_path / "also-missing")


def test_workspace_fingerprint_shape(tmp_path):
    a = _py_repo(tmp_path / "a", "a")
    b = _py_repo(tmp_path / "b", "b")
    stamp = workspace_fingerprint({"a": a, "b": b})
    assert stamp["schema"] == SCHEMA
    assert set(stamp["repos"]) == {"a", "b"}
    assert isinstance(stamp["root"], str) and len(stamp["root"]) == 64


# --- comparison ---


def test_compare_fresh_when_identical(tmp_path):
    a = _py_repo(tmp_path / "a", "a")
    stamp = workspace_fingerprint({"a": a})
    report = compare_freshness(stamp, workspace_fingerprint({"a": a}))
    assert report["verdict"] == "FRESH"
    assert report["repos_changed"] == []


def test_compare_detects_change_add_remove(tmp_path):
    a = _py_repo(tmp_path / "a", "a")
    b = _py_repo(tmp_path / "b", "b")
    stamp = workspace_fingerprint({"a": a, "b": b})
    # change a, remove b, add c
    (a / "main.py").write_text("y = 9\n", encoding="utf-8")
    c = _py_repo(tmp_path / "c", "c")
    report = compare_freshness(stamp, workspace_fingerprint({"a": a, "c": c}))
    assert report["verdict"] == "STALE"
    assert report["repos_changed"] == ["a"]
    assert report["repos_removed"] == ["b"]
    assert report["repos_added"] == ["c"]


def test_compare_rejects_non_freshness_document():
    with pytest.raises(ValueError):
        compare_freshness({"schema": "nope"}, {"schema": SCHEMA, "repos": {}, "root": "x"})


# --- CLI: stamp and re-check ---


def test_check_without_freshness_has_no_stamp(tmp_path, capsys):
    _py_repo(tmp_path / "app", "app")
    rc = main(["check", "--root", str(tmp_path), "--json"])
    assert rc in (0, 1)  # UNVERIFIABLE prints rc 1 here (no criterion), that is fine
    cert = json.loads(capsys.readouterr().out)
    assert "freshness" not in cert  # back-compat: absent unless asked


def test_check_with_freshness_stamps_certificate(tmp_path, capsys):
    _py_repo(tmp_path / "app", "app")
    main(["check", "--root", str(tmp_path), "--freshness", "--json"])
    cert = json.loads(capsys.readouterr().out)
    assert cert["freshness"]["schema"] == SCHEMA
    assert "app" in cert["freshness"]["repos"]


def test_freshness_fresh_then_stale(tmp_path, capsys):
    app = _py_repo(tmp_path / "app", "app")
    main(["check", "--root", str(tmp_path), "--freshness", "--json"])
    cert_text = capsys.readouterr().out
    cert_file = tmp_path / "cert.json"
    cert_file.write_text(cert_text, encoding="utf-8")

    # unchanged -> FRESH, exit 0
    rc = main(["freshness", "--cert", str(cert_file), "--root", str(tmp_path)])
    assert rc == 0
    assert "FRESH" in capsys.readouterr().out

    # edit a source file -> STALE, exit 1, names the repo
    (app / "main.py").write_text("import sys\nz = 3\n", encoding="utf-8")
    rc = main(["freshness", "--cert", str(cert_file), "--root", str(tmp_path), "--json"])
    assert rc == 1
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "STALE"
    assert "app" in report["repos_changed"]
    assert report["recheck"].startswith("index freshness")


def test_freshness_unverifiable_without_stamp(tmp_path, capsys):
    _py_repo(tmp_path / "app", "app")
    cert_file = tmp_path / "plain.json"
    # a certificate with no freshness stamp
    cert_file.write_text(json.dumps({"schema": "index.certificate/1", "verdict": "MATCH"}),
                         encoding="utf-8")
    rc = main(["freshness", "--cert", str(cert_file), "--root", str(tmp_path)])
    assert rc == 2
    assert "UNVERIFIABLE" in capsys.readouterr().out


def test_every_resolver_declares_a_fingerprint_footprint():
    """Drift guard: each resolver contributes at least one relevant-file matcher,
    so the fingerprint cannot silently stop tracking an ecosystem."""
    from index_graph.graph.resolvers import ALL_RESOLVERS
    for r in ALL_RESOLVERS:
        footprint = (getattr(r, "fingerprint_names", ())
                     + getattr(r, "fingerprint_suffixes", ())
                     + getattr(r, "fingerprint_globs", ()))
        assert footprint, f"{r.name} declares no fingerprint footprint"
