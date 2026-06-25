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
