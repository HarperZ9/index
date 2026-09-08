import os
import json
import subprocess
import sys
from pathlib import Path

from index_graph.knowledge.docs import discover_router_docs
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


def test_router_caps_doc_edges_with_omission_notice():
    pack = {
        "repos": [{"name": "core"}],
        "roles": {},
        "relations": [],
        "knowledge_edges": [
            {"type": "describes", "from": f"docs/{i}.md", "to": "core", "to_kind": "repo"}
            for i in range(3)
        ],
    }
    out = render_router(pack, max_docs=1)
    assert "`docs/0.md` describes `core`" in out
    assert "`docs/1.md` describes `core`" not in out
    assert "2 doc edge(s) omitted" in out


def test_router_caps_dependency_labels():
    pack = {
        "repos": [{"name": "api"}, {"name": "a"}, {"name": "b"}, {"name": "c"}],
        "roles": {"api": ["entrypoint"]},
        "relations": [
            {"from": "api", "to": "a", "external": False},
            {"from": "api", "to": "b", "external": False},
            {"from": "api", "to": "c", "external": False},
        ],
        "knowledge_edges": [],
    }
    out = render_router(pack, max_deps=2)
    assert "`api` starts here; depends on a, b, ... 1 more" in out


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
    progress = [json.loads(line) for line in r.stderr.splitlines()
                if line.startswith('{"schema": "index.graph-progress/v1"')]
    assert progress, r.stderr
    assert progress[0]["phase"] == "building"
    assert progress[-1]["phase"] == "complete"
    assert progress[-1]["completed_repos"] == progress[-1]["total_repos"] == 1
    assert "index.graph-progress" not in r.stdout


def test_router_doc_discovery_does_not_read_markdown_bodies(tmp_path, monkeypatch):
    doc = tmp_path / "pkg" / "docs" / "big.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Big\n\nbody that router does not need\n", encoding="utf-8")

    real_read_text = Path.read_text

    def fail_on_markdown_body(path: Path, *args, **kwargs):
        if path.suffix.lower() == ".md":
            raise AssertionError("router doc discovery should not read markdown bodies")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_on_markdown_body)

    docs = discover_router_docs(tmp_path)

    assert [(d.rel_path, d.dir_rel, d.title, d.body, d.link_targets) for d in docs] == [
        ("pkg/docs/big.md", "pkg/docs", "big", "", ())
    ]


def test_router_no_cache_bypasses_repo_facts_too(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from index_graph.cli_handlers import maps

    (tmp_path / "solo" / ".git").mkdir(parents=True)
    calls = []
    real_build = maps.build_graph

    def record_build(*args, **kwargs):
        calls.append(kwargs.get("use_cache"))
        return real_build(*args, **kwargs)

    monkeypatch.setattr(maps, "build_graph", record_build)
    maps.cmd_router(SimpleNamespace(root=tmp_path, max_docs=5, budget_ms=0,
                                    no_cache=True, out=None))
    assert calls == [False]
