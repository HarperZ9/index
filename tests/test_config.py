import pytest

from workspace_repo_map.config import (
    Config, Rule, default_config, glob_to_regex, load_config,
)


def _match(pattern, path):
    import re
    return re.match(glob_to_regex(pattern), path) is not None


def test_glob_double_star_matches_lane_and_nested():
    assert _match("public/**", "public")
    assert _match("public/**", "public/demo")
    assert _match("public/**", "public/demo/sub")
    assert not _match("public/**", "publicx")


def test_glob_single_star_stays_in_segment():
    assert _match("*", "data")
    assert not _match("*", "a/b")


def test_glob_dot_prefix_rule():
    assert _match(".*", ".claude")
    assert not _match(".*", "data")


def test_default_config_is_neutral():
    cfg = default_config()
    assert cfg.rules == ()
    assert cfg.portable is True
    assert cfg.omit_origin_classes == frozenset()
    assert ".git" in cfg.prune


def test_load_config_parses_rules_scan_privacy_output(tmp_path):
    (tmp_path / ".repomap.toml").write_text(
        '[[rule]]\npattern = "public/**"\nclass = "public"\n'
        '[scan]\njobs = 4\nprune = ["vendor"]\n'
        '[privacy]\nomit_origin_classes = ["protected"]\n'
        '[output]\nportable = false\nannotations = { note = "x" }\n',
        encoding="utf-8",
    )
    cfg = load_config(None, tmp_path)
    assert cfg.rules[0].class_ == "public"
    assert cfg.rules[0].regex.match("public/demo")
    assert cfg.jobs == 4
    assert "vendor" in cfg.prune and ".git" in cfg.prune  # extends, never replaces
    assert cfg.omit_origin_classes == frozenset({"protected"})
    assert cfg.portable is False
    assert cfg.annotations == {"note": "x"}


def test_load_config_absent_file_returns_defaults(tmp_path):
    assert load_config(None, tmp_path).rules == ()


def test_missing_config_path_is_fatal(tmp_path):
    with pytest.raises(SystemExit):
        load_config(tmp_path / "nope.toml", tmp_path)


def test_rule_without_class_is_fatal(tmp_path):
    (tmp_path / ".repomap.toml").write_text('[[rule]]\npattern = "x"\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        load_config(None, tmp_path)


def test_bad_jobs_is_fatal(tmp_path):
    (tmp_path / ".repomap.toml").write_text("[scan]\njobs = 0\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_config(None, tmp_path)


def test_unknown_key_warns_not_fatal(tmp_path, capsys):
    (tmp_path / ".repomap.toml").write_text('[bogus]\nx = 1\n', encoding="utf-8")
    cfg = load_config(None, tmp_path)
    assert cfg.rules == ()
    assert "unknown config key 'bogus'" in capsys.readouterr().err
