import pytest

from index_graph.arch.criteria import parse_architecture, ArchitectureCriteria


def test_empty_block_is_undeclared():
    c = parse_architecture({})
    assert isinstance(c, ArchitectureCriteria)
    assert c.declared is False


def test_layers_and_forbid_and_cycles_and_owns():
    c = parse_architecture({
        "layers": ["core", "domain", "web"],
        "forbid": [{"from": "core/**", "to": "web/**"}],
        "max_cycles": 0,
        "owns": {"payments/**": "team-payments"},
    })
    assert c.layers == ("core", "domain", "web")
    assert c.forbid[0].from_glob == "core/**"
    assert c.forbid[0].to_glob == "web/**"
    assert c.max_cycles == 0
    assert c.owns == (("payments/**", "team-payments"),)
    assert c.declared is True


def test_malformed_forbid_raises():
    with pytest.raises(SystemExit):
        parse_architecture({"forbid": [{"from": "core/**"}]})


def test_negative_max_cycles_raises():
    with pytest.raises(SystemExit):
        parse_architecture({"max_cycles": -1})
