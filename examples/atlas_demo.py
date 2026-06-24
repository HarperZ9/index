"""Fabricate a synthetic repos+docs workspace and render the atlas demo HTML.

Run:  python examples/atlas_demo.py   ->  writes examples/atlas-demo.html
Path-independent + deterministic (uses repo names + workspace-relative doc paths only).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from index_graph import viz
from index_graph.config import load_config
from index_graph.graph.build import build_graph
from index_graph.knowledge.atlas import build_atlas_pack
from index_graph.knowledge.docs import discover_docs
from index_graph.scan import discover_repos


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def build_workspace(root: Path) -> None:
    _w(root / "storage" / ".git", "")
    _w(root / "storage" / "pyproject.toml", '[project]\nname = "storage"\nversion = "0.1.0"\n')
    _w(root / "storage" / "storage.py", "def get(k):\n    return k\n")
    _w(root / "storage" / "README.md", "# Storage\n\nDurable key-value core. See [[Architecture]].\n")
    _w(root / "api" / ".git", "")
    _w(root / "api" / "pyproject.toml", '[project]\nname = "api"\nversion = "0.1.0"\ndependencies = ["storage"]\n')
    _w(root / "api" / "api.py", "import storage\n")
    _w(root / "api" / "README.md", "# API\n\nHTTP surface over [[Storage]].\n\n- follows the [[Architecture]]\n- [x] auth\n- [ ] rate limits\n")
    _w(root / "docs" / "architecture.md",
       "# Architecture\n\n## Overview\n\n`api` is the entry; `storage` is the core. See [[API]] and [[Storage]].\n\n"
       "> Rule: api never imports a peer API.\n")
    _w(root / "docs" / "adr-001-storage.md",
       "# ADR 001: Storage\n\n| option | verdict |\n| --- | --- |\n| sqlite | chosen |\n| flat files | rejected |\n")


def render(root: Path) -> str:
    root = root.resolve()
    config = load_config(None, root)
    repo_paths = {p.name: p for p in discover_repos(root, config)}
    repo_dirs = {}
    for name, p in repo_paths.items():
        rel = p.resolve().relative_to(root).as_posix()
        repo_dirs[name] = "" if rel == "." else rel
    docs = discover_docs(root)
    pack = build_atlas_pack(build_graph(repo_paths), docs, repo_dirs)
    svg = viz.render_atlas_svg(viz.build_atlas_layout(pack))
    return viz.render_atlas_html(pack, docs, svg=svg)


def main() -> None:
    out = Path(__file__).resolve().parent / "atlas-demo.html"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_workspace(root)
        html = render(root)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
