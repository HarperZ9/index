from index_graph.drift import snapshot_pack, diff_snapshots


def _pack(relations, roles, cycles=None):
    return {"relations": relations, "roles": roles, "cycles": cycles or []}


def test_snapshot_is_sorted_and_minimal():
    pack = _pack(
        relations=[{"from": "b", "to": "a", "external": False, "confidence": "high", "signals": []},
                   {"from": "a", "to": "c", "external": False, "confidence": "low", "signals": []}],
        roles={"b": ["hub"], "a": []},
    )
    snap = snapshot_pack(pack)
    assert snap["edges"] == ["a -> c", "b -> a"]
    assert snap["roles"] == {"a": [], "b": ["hub"]}


def test_diff_detects_added_removed_edges():
    old = snapshot_pack(_pack([{"from": "a", "to": "b", "external": False, "confidence": "high", "signals": []}], {"a": [], "b": []}))
    new = snapshot_pack(_pack([{"from": "a", "to": "c", "external": False, "confidence": "high", "signals": []}], {"a": [], "c": []}))
    report = diff_snapshots(old, new)
    assert report.edges_added == ("a -> c",)
    assert report.edges_removed == ("a -> b",)
    assert report.repos_added == ("c",)
    assert report.repos_removed == ("b",)
    assert report.verdict == "DRIFT"


def test_identical_snapshots_match():
    snap = snapshot_pack(_pack([{"from": "a", "to": "b", "external": False, "confidence": "high", "signals": []}], {"a": [], "b": []}))
    assert diff_snapshots(snap, snap).verdict == "MATCH"


def test_cycles_introduced_and_roles_changed():
    old = snapshot_pack(_pack([], {"a": ["leaf"]}, cycles=[]))
    new = snapshot_pack(_pack([], {"a": ["hub"]}, cycles=[["a", "b"]]))
    report = diff_snapshots(old, new)
    assert report.cycles_introduced == (("a", "b"),)
    assert ("a", "leaf", "hub") in report.roles_changed
