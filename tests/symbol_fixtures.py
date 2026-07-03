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


def inheritance(root: Path) -> Path:
    """Base.speak() overridden by an imported subclass Dog, plus a same-module
    subclass Cat that also overrides speak(). Base declares a second method
    ``legs`` that neither child overrides (so it has zero implementations)."""
    write(root, "base.py",
          "class Animal:\n"
          "    def speak(self):\n"
          "        pass\n\n"
          "    def legs(self):\n"
          "        return 4\n")
    write(root, "dog.py",
          "from base import Animal\n\n\n"
          "class Dog(Animal):\n"
          "    def speak(self):\n"
          "        return \"woof\"\n")
    write(root, "cat.py",
          "from base import Animal\n\n\n"
          "class Cat(Animal):\n"
          "    def speak(self):\n"
          "        return \"meow\"\n")
    return root
