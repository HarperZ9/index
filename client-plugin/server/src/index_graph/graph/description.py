"""Repository description extraction for graph nodes."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from .walk import read_source_text

_PARA = re.compile(r"\n\s*\n")


def description(repo_root: Path) -> str:
    for readme in ("README.md", "README.rst", "README.txt", "readme.md"):
        p = repo_root / readme
        if p.is_file():
            try:
                text = read_source_text(p, encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            for block in _PARA.split(text):
                b = block.strip()
                if b and not b.startswith("#") and not b.startswith("!["):
                    return " ".join(b.split())[:300]
    pp = repo_root / "pyproject.toml"
    if pp.is_file():
        try:
            d = tomllib.loads(read_source_text(pp, encoding="utf-8", errors="replace")).get("project", {})
            if d.get("description"):
                return str(d["description"])
        except (tomllib.TOMLDecodeError, OSError):
            pass
    pj = repo_root / "package.json"
    if pj.is_file():
        try:
            d = json.loads(read_source_text(pj, encoding="utf-8", errors="replace"))
            if d.get("description"):
                return str(d["description"])
        except (json.JSONDecodeError, OSError):
            pass
    return "(no description)"
