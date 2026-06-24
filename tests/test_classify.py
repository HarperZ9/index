from index_graph.classify import classify
from index_graph.config import Config, Rule


def test_first_matching_rule_wins():
    cfg = Config(rules=(Rule("public/**", "public"), Rule("**", "workspace")))
    assert classify("public/demo", True, "", cfg) == "public"
    assert classify("other/repo", True, "", cfg) == "workspace"


def test_fallback_ladder_for_repos():
    cfg = Config()
    assert classify("x", True, "", cfg) == "local"
    assert classify("x", True, "https://github.com/o/r.git", cfg) == "public"
    assert classify("x", True, "git@github.com:o/r.git", cfg) == "public"
    assert classify("x", True, "https://git.example.com/o/r.git", cfg) == "private"


def test_root_entry_fallback():
    cfg = Config()
    assert classify(".cache", False, "", cfg) == "hidden"
    assert classify("notes", False, "", cfg) == "entry"
