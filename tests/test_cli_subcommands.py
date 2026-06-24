from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from index_graph.cli import main

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def workspace(tmp_path):
    for name in ("py-lib", "py-app"):
        dst = tmp_path / name
        shutil.copytree(FIX / name, dst)
        (dst / ".git").mkdir()   # makes it a discoverable repo at runtime
    return tmp_path


def test_backward_compat_bare_invocation_writes_map(tmp_path, capsys):
    rc = main(["--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "repositories" in data  # the existing map shape


def test_graph_subcommand_json(workspace, capsys):
    rc = main(["graph", "--root", str(workspace), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "relations" in data and "roles" in data


def test_context_focus_unknown_returns_2(workspace, capsys):
    rc = main(["context", "--root", str(workspace), "--focus", "nope-xyz"])
    assert rc == 2


def test_context_focus_known(workspace, capsys):
    rc = main(["context", "--root", str(workspace), "--focus", "py-lib"])
    out = capsys.readouterr().out
    assert rc == 0 and "## Relations" in out
