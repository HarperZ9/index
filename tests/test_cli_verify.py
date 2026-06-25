import json
import os
import subprocess
import sys
from pathlib import Path


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    return env


def _run(args):
    return subprocess.run(
        [sys.executable, "-m", "index_graph", *args],
        cwd=Path.cwd(), capture_output=True, text=True, env=_env())


def test_internals_json_runs(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "a.py").write_text("from .b import x\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("x = 1\n", encoding="utf-8")
    r = _run(["internals", "--root", str(tmp_path), "--json"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert any(e["from"] == "pkg/a" and e["to"] == "pkg/b" for e in data["edges"])


def test_check_unverifiable_without_criterion(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    r = _run(["check", "--root", str(tmp_path), "--json"])
    cert = json.loads(r.stdout)
    assert cert["verdict"] == "UNVERIFIABLE"
    assert cert["schema"] == "index.certificate/1"
    assert cert["criterion_sha256"] is None


def test_check_emits_certificate_with_criterion(tmp_path):
    (tmp_path / ".index.toml").write_text("[architecture]\nmax_cycles = 0\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    r = _run(["check", "--root", str(tmp_path), "--json"])
    cert = json.loads(r.stdout)
    assert cert["schema"] == "index.certificate/1"
    assert cert["verdict"] in ("MATCH", "DRIFT", "UNVERIFIABLE")
    assert cert["criterion_sha256"] is not None


def test_snapshot_then_drift_roundtrip(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    out = tmp_path / "snap.json"
    r1 = _run(["snapshot", "--root", str(tmp_path), "--out", str(out)])
    assert r1.returncode == 0, r1.stderr
    assert out.is_file()
    r2 = _run(["drift", "--from", str(out), "--to", str(out), "--json"])
    assert r2.returncode == 0, r2.stderr
    report = json.loads(r2.stdout)
    assert report["verdict"] == "MATCH"


def test_check_internals_finds_internal_cycle_and_outranks_unverifiable(tmp_path):
    # A repo with an internal module cycle. The bare repo-level check sees no
    # cycle and an unmatched 'ghost' layer -> UNVERIFIABLE. With --internals the
    # real internal cycle is a confirmed breach, which must outrank UNVERIFIABLE.
    repo = tmp_path / "myrepo"
    (repo / "pkg").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "a.py").write_text("from . import b\n", encoding="utf-8")
    (repo / "pkg" / "b.py").write_text("from . import a\n", encoding="utf-8")
    (tmp_path / ".index.toml").write_text(
        "[architecture]\nmax_cycles = 0\nlayers = ['ghost']\n", encoding="utf-8")

    bare = json.loads(_run(["check", "--root", str(tmp_path), "--json"]).stdout)
    deep = json.loads(_run(["check", "--root", str(tmp_path), "--internals", "--json"]).stdout)

    assert bare["verdict"] == "UNVERIFIABLE"
    assert deep["verdict"] == "DRIFT"
    assert any(f["rule"] == "max_cycles" for f in deep["findings"])
    # the certificate's content hash must cover the internals it checked
    assert deep["content_sha256"] != bare["content_sha256"]


def test_internals_json_reports_coverage(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "broken.py").write_text("def (:\n", encoding="utf-8")
    data = json.loads(_run(["internals", "--root", str(tmp_path), "--json"]).stdout)
    assert data["coverage"]["complete"] is False
    assert "pkg/broken.py" in data["coverage"]["parse_errors"]


def test_check_internals_certificate_carries_coverage(tmp_path):
    # a MATCH that is honest about what it could not verify (soundness-typed)
    repo = tmp_path / "myrepo"
    (repo / "pkg").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "broken.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / ".index.toml").write_text("[architecture]\nmax_cycles = 0\n", encoding="utf-8")
    cert = json.loads(_run(["check", "--root", str(tmp_path), "--internals", "--json"]).stdout)
    assert "coverage" in cert
    assert cert["coverage"]["complete"] is False
    assert "myrepo" in cert["coverage"]["unverifiable_repos"]


def test_check_require_absence_is_drift(tmp_path):
    # two repos exist; a required edge between them is missing -> absence -> DRIFT
    for name in ("web", "core"):
        (tmp_path / name / ".git").mkdir(parents=True)
        (tmp_path / name / "pyproject.toml").write_text(
            f"[project]\nname='{name}'\nversion='0'\n", encoding="utf-8")
    (tmp_path / ".index.toml").write_text(
        "[architecture]\nrequire = [{from = 'web', to = 'core'}]\n", encoding="utf-8")
    cert = json.loads(_run(["check", "--root", str(tmp_path), "--json"]).stdout)
    assert cert["verdict"] == "DRIFT"
    assert any(f["rule"] == "absence" for f in cert["findings"])


def test_empty_require_does_not_change_criterion_hash(tmp_path):
    # a criterion with no require rule must hash exactly as it did before require existed
    from index_graph.certify import canonical_sha
    (tmp_path / ".index.toml").write_text("[architecture]\nmax_cycles = 0\n", encoding="utf-8")
    cert = json.loads(_run(["check", "--root", str(tmp_path), "--json"]).stdout)
    expected = canonical_sha({"layers": [], "forbid": [], "max_cycles": 0, "owns": []})
    assert cert["criterion_sha256"] == expected
