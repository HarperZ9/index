"""`index wiki <source>`: a local path or a git URL (shallow-cloned, then removed)."""
import json

import pytest

from index_graph.cli import main

from wiki_fixtures import git_commit_all, make_repo


def test_local_path_source_is_used_over_root(tmp_path, capsys):
    root = make_repo(tmp_path / "demo")
    # No --root: the positional source is the repo.
    assert main(["wiki", str(root), "--format", "json"]) == 0
    pack = json.loads(capsys.readouterr().out)
    assert pack["schema"] == "index.wiki/1"
    assert {p["id"] for p in pack["pages"]} >= {"overview", "architecture", "docs"}


def test_file_url_source_is_cloned_and_cleaned_up(tmp_path, capsys):
    root = make_repo(tmp_path / "demo")
    git_commit_all(root)
    before = {p.name for p in tmp_path.iterdir()}

    assert main(["wiki", root.as_uri(), "--format", "json"]) == 0
    pack = json.loads(capsys.readouterr().out)
    assert pack["schema"] == "index.wiki/1"

    # The shallow clone went to a system temp dir, not next to the source, and
    # nothing new was left behind in the working area.
    assert {p.name for p in tmp_path.iterdir()} == before


def test_non_url_non_dir_source_is_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["wiki", "not-a-url-or-a-real-directory"])
    assert "not a git URL or an existing directory" in str(exc.value)


def test_unclonable_url_fails_closed(tmp_path):
    missing = (tmp_path / "does-not-exist").as_uri()
    with pytest.raises(SystemExit) as exc:
        main(["wiki", missing])
    assert "could not clone" in str(exc.value)
