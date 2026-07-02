"""Fabricate a synthetic single repo and render the verified-wiki demo HTML.

Run:  python examples/wiki_demo.py   ->  writes examples/wiki-demo.html
Path-independent + deterministic: the repo directory has a fixed name, no
git history (the wiki pins "unversioned"), and every path in the artifact
is repo-relative. The generator verifies its own artifact before writing;
a pack that does not come back MATCH is a failed build, not a demo.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from index_graph.wiki.html import render_wiki_html  # noqa: E402
from index_graph.wiki.pack import build_wiki_pack  # noqa: E402
from index_graph.wiki.seal import verify_wiki  # noqa: E402

REPO_NAME = "miniweb"


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def build_repo(root: Path) -> Path:
    repo = root / REPO_NAME
    _w(repo / "app.py", "import router\nimport storage\n")
    _w(repo / "router.py", "import models\nimport storage\n")
    _w(repo / "storage.py", "import models\n\n\ndef get(key):\n    return key\n")
    _w(repo / "models.py", "class Record:\n    pass\n")
    _w(repo / "README.md",
       "# miniweb\n\nA tiny demo service: `app` is the entry point, `router` "
       "dispatches, `storage` persists, `models` holds the shared records.\n")
    _w(repo / "docs" / "architecture.md",
       "# Architecture\n\n`app` calls `router`; `router` and `storage` share "
       "`models`.\n\n> Rule: `models` imports nothing.\n")
    _w(repo / "docs" / "adr-001-storage.md",
       "# ADR 001: Storage\n\n| option | verdict |\n| --- | --- |\n"
       "| in-memory dict | chosen |\n| external service | rejected |\n")
    return repo


def render(repo: Path) -> str:
    pack = build_wiki_pack(repo)
    report = verify_wiki(pack, repo)
    if report["verdict"] != "MATCH":
        raise SystemExit(f"wiki demo failed self-verification: {report['findings']}")
    return render_wiki_html(pack)


def main() -> None:
    out = Path(__file__).resolve().parent / "wiki-demo.html"
    with tempfile.TemporaryDirectory() as tmp:
        html = render(build_repo(Path(tmp)))
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
