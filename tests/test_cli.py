import json

import pytest

from index_graph.cli import main


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "2.8.0" in capsys.readouterr().out


def test_json_to_stdout(tmp_path, capsys):
    (tmp_path / "demo" / ".git").mkdir(parents=True)
    assert main(["--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1


def test_writes_default_output(tmp_path):
    (tmp_path / "demo" / ".git").mkdir(parents=True)
    assert main(["--root", str(tmp_path)]) == 0
    assert (tmp_path / "INDEX.json").exists()


def test_missing_config_is_fatal(tmp_path):
    with pytest.raises(SystemExit):
        main(["--root", str(tmp_path), "--config", str(tmp_path / "nope.toml")])


def test_public_api_surface():
    import index_graph as pkg
    for name in ("build_map", "Map", "RepoRow", "Config", "Rule", "load_config", "classify"):
        assert name in pkg.__all__
        assert hasattr(pkg, name)
