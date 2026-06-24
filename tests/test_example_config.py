from pathlib import Path

from index_graph.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_example_config_parses():
    cfg = load_config(REPO_ROOT / "example.repomap.toml", REPO_ROOT)
    assert cfg.rules  # has at least one rule
    assert all(rule.regex for rule in cfg.rules)
