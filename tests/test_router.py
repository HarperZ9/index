import os
import subprocess
import sys
from pathlib import Path

from index_graph.router import render_router


def _run(args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path("src").resolve())
    return subprocess.run([sys.executable, "-m", "index_graph", *args],
                          cwd=Path.cwd(), capture_output=True, text=True, env=env)


def test_router_renders_sections():
    pack = {
        "repos": [{"name": "api"}, {"name": "core"}, {"name": "web"}],
        "roles": {"api": ["entrypoint"], "core": ["hub", "library"], "web": ["entrypoint"]},
        "relations": [
            {"from": "api", "to": "core", "external": False},
            {"from": "web", "to": "core", "external": False},
        ],
        "knowledge_edges": [
            {"type": "describes", "from": "core/README.md", "to": "core", "to_kind": "repo"},
        ],
    }
    out = render_router(pack)
    assert "# Workspace map" in out
    assert "## Entry points" in out
    assert "`api` starts here; depends on core" in out
    assert "## Core (most depended-on" in out
    assert "`core` is used by api, web" in out
    assert "## Where things live" in out
    assert "## Docs" in out
    assert "`core/README.md` describes `core`" in out

def test_router_includes_dependency_evidence_compactly():
    pack = {
        "repos": [{"name": "api"}, {"name": "core"}, {"name": "web"}],
        "roles": {"api": ["entrypoint"], "core": ["hub"], "web": ["entrypoint"]},
        "relations": [
            {"from": "api", "to": "core", "external": False,
             "signals": [{"file": "api/pyproject.toml", "line": 4}]},
            {"from": "web", "to": "core", "external": False,
             "signals": [{"file": "web/package.json", "line": None}]},
        ],
        "knowledge_edges": [],
    }
    out = render_router(pack)
    assert "`api` starts here; depends on core [api/pyproject.toml:4]" in out
    assert "`web` starts here; depends on core [web/package.json]" in out
    assert "`api` (entrypoint); depends on core [api/pyproject.toml:4]" in out

def test_router_is_deterministic_and_sorted():
    pack = {
        "repos": [{"name": "b"}, {"name": "a"}],
        "roles": {},
        "relations": [{"from": "a", "to": "b", "external": False}],
        "knowledge_edges": [],
    }
    assert render_router(pack) == render_router(pack)
    out = render_router(pack)
    assert out.index("`a`") < out.index("`b`")


def test_router_omits_empty_sections():
    pack = {"repos": [{"name": "solo"}], "roles": {}, "relations": [], "knowledge_edges": []}
    out = render_router(pack)
    assert "## Entry points" not in out
    assert "## Core" not in out
    assert "## Docs" not in out
    assert "`solo` (unclassified)" in out


def test_negative_hops_rejected(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    r = _run(["context", "--root", str(tmp_path), "--hops", "-1"])
    assert r.returncode != 0
    assert "hops" in (r.stderr + r.stdout).lower()


def test_router_cli_smoke(tmp_path):
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    (tmp_path / "solo" / "pyproject.toml").write_text(
        "[project]\nname='solo'\nversion='0'\n", encoding="utf-8")
    r = _run(["router", "--root", str(tmp_path)])
    assert r.returncode == 0, r.stderr
    assert "# Workspace map" in r.stdout
    assert "solo" in r.stdout
