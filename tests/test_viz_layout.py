from workspace_repo_map.viz.layout import build_layout, ROLE_PRECEDENCE
from viz_fixtures import simple_pack, cyclic_pack


def _node(layout, name):
    return next(n for n in layout.nodes if n.name == name)


def test_primary_role_drives_layer_assignment():
    layout = build_layout(simple_pack())
    assert _node(layout, "web").layer == ROLE_PRECEDENCE.index("entrypoint")
    assert _node(layout, "api").layer == ROLE_PRECEDENCE.index("orchestrator")
    assert _node(layout, "core").layer == ROLE_PRECEDENCE.index("hub")
    assert _node(layout, "lib").layer == ROLE_PRECEDENCE.index("library")


def test_external_target_becomes_a_terminal_node_when_included():
    layout = build_layout(simple_pack(), include_external=True)
    ext = _node(layout, "requests")
    assert ext.external is True
    assert ext.layer == len(ROLE_PRECEDENCE)  # the terminal external band


def test_external_can_be_excluded():
    layout = build_layout(simple_pack(), include_external=False)
    assert all(n.name != "requests" for n in layout.nodes)
    assert all(not e.external for e in layout.edges)


def test_salience_is_carried_onto_nodes():
    layout = build_layout(simple_pack())
    assert _node(layout, "core").hub is True
    assert _node(layout, "api").in_degree == 1


def test_within_layer_order_is_stable_and_name_tiebroken():
    # two entrypoints, no neighbours to barycentre -> alphabetical, deterministic
    pack = simple_pack()
    pack["roles"]["aaa"] = ["entrypoint"]
    pack["repos"].append({"name": "aaa", "ecosystems": ["python"], "description": "", "markers": []})
    pack["salience"]["aaa"] = {"in_degree": 0, "out_degree": 0, "hub": False}
    layout = build_layout(pack)
    entry = [n.name for n in sorted(layout.nodes, key=lambda n: n.order) if n.layer == 0]
    assert entry == ["aaa", "web"]
