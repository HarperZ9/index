from index_graph.arch.criteria import ArchitectureCriteria, ForbidRule, RequireRule
from index_graph.arch.check import check_graph, Finding


def _pack(relations, roles=None, cycles=None):
    return {"relations": relations, "roles": roles or {}, "cycles": cycles or []}


def test_forbid_edge_violation():
    pack = _pack([
        {"from": "core", "to": "web", "external": False, "confidence": "high",
         "signals": [{"file": "core/x.py", "line": 3}]},
    ])
    crit = ArchitectureCriteria(forbid=(ForbidRule("core", "web"),))
    findings = check_graph(pack, crit)
    assert any(f.rule == "forbid" and f.edge == "core -> web" for f in findings)
    assert findings[0].evidence == "core/x.py:3"


def test_layer_upward_import_violation():
    pack = _pack([
        {"from": "core", "to": "web", "external": False, "confidence": "high", "signals": []},
    ])
    crit = ArchitectureCriteria(layers=("core", "web"))
    findings = check_graph(pack, crit)
    assert any(f.rule == "layer" for f in findings)


def test_layer_downward_import_allowed():
    pack = _pack([
        {"from": "web", "to": "core", "external": False, "confidence": "high", "signals": []},
    ])
    crit = ArchitectureCriteria(layers=("core", "web"))
    assert [f for f in check_graph(pack, crit) if f.rule == "layer"] == []


def test_max_cycles_breach():
    pack = _pack([], cycles=[["a", "b"], ["c", "d"]])
    crit = ArchitectureCriteria(max_cycles=1)
    findings = check_graph(pack, crit)
    assert any(f.rule == "max_cycles" for f in findings)


def test_clean_graph_no_findings():
    pack = _pack([{"from": "web", "to": "core", "external": False, "confidence": "high", "signals": []}],
                 cycles=[])
    crit = ArchitectureCriteria(layers=("core", "web"), max_cycles=0)
    assert check_graph(pack, crit) == []


def test_absence_when_required_edge_missing():
    # web and core both exist as repos, but web does not depend on core
    pack = _pack([{"from": "web", "to": "api", "external": False, "confidence": "high", "signals": []}],
                 roles={"web": [], "api": [], "core": []})
    crit = ArchitectureCriteria(require=(RequireRule("web", "core"),))
    findings = check_graph(pack, crit)
    assert any(f.rule == "absence" for f in findings)


def test_require_unmatched_when_endpoint_absent():
    # 'ghost' is not in the workspace: a criterion-quality gap, not a confirmed absence
    pack = _pack([{"from": "web", "to": "api", "external": False, "confidence": "high", "signals": []}],
                 roles={"web": [], "api": []})
    crit = ArchitectureCriteria(require=(RequireRule("web", "ghost"),))
    findings = check_graph(pack, crit)
    assert any(f.rule == "require_unmatched" for f in findings)
    assert not any(f.rule == "absence" for f in findings)


def test_convergence_when_required_edge_present():
    pack = _pack([{"from": "web", "to": "core", "external": False, "confidence": "high", "signals": []}])
    crit = ArchitectureCriteria(require=(RequireRule("web", "core"),))
    assert [f for f in check_graph(pack, crit) if f.rule == "absence"] == []
