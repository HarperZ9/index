from __future__ import annotations

import json
from pathlib import Path

from workspace_repo_map.cli import main

FIX = Path(__file__).parent / "fixtures"


def test_backward_compat_bare_invocation_writes_map(tmp_path, capsys):
    rc = main(["--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "repositories" in data  # the existing map shape


def test_graph_subcommand_json(capsys):
    rc = main(["graph", "--root", str(FIX), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "relations" in data and "roles" in data


def test_context_focus_unknown_returns_2(capsys):
    rc = main(["context", "--root", str(FIX), "--focus", "nope-xyz"])
    assert rc == 2


def test_context_focus_known(capsys):
    rc = main(["context", "--root", str(FIX), "--focus", "py-lib"])
    out = capsys.readouterr().out
    assert rc == 0 and "## Relations" in out
