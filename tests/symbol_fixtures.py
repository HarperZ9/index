"""Shared synthetic fixtures for the symbol-graph tests."""
from __future__ import annotations

from pathlib import Path


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def simple_module(root: Path) -> Path:
    """One module where bar() calls foo() within the same file."""
    write(root, "mod.py", "def foo():\n    pass\n\n\ndef bar():\n    foo()\n")
    return root


def cross_module(root: Path) -> Path:
    """app.main() calls exported() imported from lib."""
    write(root, "lib.py", "def exported():\n    pass\n")
    write(root, "app.py", "from lib import exported\n\n\ndef main():\n    exported()\n")
    return root
