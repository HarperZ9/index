from index_graph.config import load_config


def test_architecture_block_parsed(tmp_path):
    (tmp_path / ".index.toml").write_text(
        "[architecture]\nlayers = ['core', 'web']\nmax_cycles = 0\n", encoding="utf-8")
    cfg = load_config(None, tmp_path)
    assert cfg.architecture.layers == ("core", "web")
    assert cfg.architecture.max_cycles == 0


def test_absent_block_is_undeclared(tmp_path):
    cfg = load_config(None, tmp_path)
    assert cfg.architecture.declared is False


def test_bom_prefixed_config_is_tolerated(tmp_path):
    import codecs
    (tmp_path / ".index.toml").write_bytes(
        codecs.BOM_UTF8 + b"[architecture]\nmax_cycles = 0\n")
    cfg = load_config(None, tmp_path)
    assert cfg.architecture.max_cycles == 0
