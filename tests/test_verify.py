import json
import os
import subprocess
import sys
from pathlib import Path

from index_graph.verify import verify_claim, build_verification


def _run(args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    return subprocess.run([sys.executable, "-m", "index_graph", *args],
                          cwd=Path.cwd(), capture_output=True, text=True, env=env)


def _pack(relations, roles):
    return {"relations": relations, "roles": roles}


def test_depends_match_with_evidence():
    pack = _pack([{"from": "api", "to": "core", "external": False,
                   "signals": [{"file": "api/main.py", "line": 3}]}],
                 {"api": [], "core": []})
    r = verify_claim(pack, {"kind": "depends", "from": "api", "to": "core"})
    assert r["verdict"] == "MATCH"
    assert r["evidence"] == "api/main.py:3"


def test_depends_refuted_when_no_edge():
    pack = _pack([{"from": "api", "to": "core", "external": False, "signals": []}],
                 {"api": [], "core": [], "web": []})
    r = verify_claim(pack, {"kind": "depends", "from": "web", "to": "core"})
    assert r["verdict"] == "REFUTED"


def test_depends_unverifiable_when_repo_absent():
    pack = _pack([], {"api": []})
    r = verify_claim(pack, {"kind": "depends", "from": "api", "to": "ghost"})
    assert r["verdict"] == "UNVERIFIABLE"


def test_exists_match_and_refuted():
    pack = _pack([], {"api": []})
    assert verify_claim(pack, {"kind": "exists", "name": "api"})["verdict"] == "MATCH"
    assert verify_claim(pack, {"kind": "exists", "name": "ghost"})["verdict"] == "REFUTED"


def test_build_verification_shape():
    pack = _pack([], {"api": []})
    rec = build_verification(pack, {"kind": "exists", "name": "api"},
                             tool_version="9.9.9", recheck="index verify ...")
    assert rec["schema"] == "index.verification/1"
    assert rec["verdict"] == "MATCH"
    assert rec["content_sha256"]
    assert rec["recheck"] == "index verify ..."


def test_verify_cli_exists_and_refuted(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    r = _run(["verify", "--root", str(tmp_path), "--exists", "solo", "--json"])
    assert r.returncode == 0, r.stderr
    rec = json.loads(r.stdout)
    assert rec["verdict"] == "MATCH"
    assert rec["schema"] == "index.verification/1"
    r2 = _run(["verify", "--root", str(tmp_path), "--exists", "ghost"])
    assert r2.returncode == 1  # REFUTED
    assert "REFUTED" in r2.stdout


def test_verify_strongest_edge_evidence():
    pack = _pack(
        [{"from": "a", "to": "b", "external": False, "confidence": "low",
          "signals": [{"file": "a/z.py", "line": 1}]},
         {"from": "a", "to": "b", "external": False, "confidence": "high",
          "signals": [{"file": "a/m.py", "line": 9}]}],
        {"a": [], "b": []})
    r = verify_claim(pack, {"kind": "depends", "from": "a", "to": "b"})
    assert r["verdict"] == "MATCH"
    assert r["evidence"] == "a/m.py:9"  # the high-confidence edge, not the first by name
    assert "2 edges agree" in r["detail"]


def test_verify_cli_depends_match_and_unverifiable(tmp_path):
    (tmp_path / "core" / ".git").mkdir(parents=True)
    (tmp_path / "core" / "pyproject.toml").write_text(
        "[project]\nname='core'\nversion='0'\n", encoding="utf-8")
    (tmp_path / "core" / "core").mkdir()
    (tmp_path / "core" / "core" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "web" / ".git").mkdir(parents=True)
    (tmp_path / "web" / "pyproject.toml").write_text(
        "[project]\nname='web'\nversion='0'\ndependencies=['core']\n", encoding="utf-8")
    # no spaces around the arrow, exercising the strip; web depends on core via its manifest
    r = _run(["verify", "--root", str(tmp_path), "--depends", "web->core"])
    assert r.returncode == 0, r.stderr
    assert "MATCH" in r.stdout
    # UNVERIFIABLE exit code 2 pinned
    r2 = _run(["verify", "--root", str(tmp_path), "--depends", "web -> ghost"])
    assert r2.returncode == 2
    assert "UNVERIFIABLE" in r2.stdout
