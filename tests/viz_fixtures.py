"""Shared pack-shaped fixtures for viz tests (mirrors context.pack.to_json output)."""


def _edge(frm, to, *, target=None, external=False, confidence="high", signals=None):
    return {
        "from": frm,
        "to": to,
        "target_name": target if target is not None else (to if to else "ext"),
        "external": external,
        "confidence": confidence,
        "signals": signals or [{"kind": "import", "file": "m.py", "line": 1, "raw": "import x"}],
    }


def simple_pack():
    """web -> api -> core -> lib ; lib -> (external) requests."""
    return {
        "roles": {
            "web": ["entrypoint"],
            "api": ["orchestrator"],
            "core": ["hub"],
            "lib": ["library"],
        },
        "relations": [
            _edge("web", "api"),
            _edge("api", "core"),
            _edge("core", "lib"),
            _edge("lib", None, target="requests", external=True, confidence="moderate"),
        ],
        "salience": {
            "web": {"in_degree": 0, "out_degree": 1, "hub": False},
            "api": {"in_degree": 1, "out_degree": 1, "hub": False},
            "core": {"in_degree": 1, "out_degree": 1, "hub": True},
            "lib": {"in_degree": 1, "out_degree": 1, "hub": False},
        },
        "salience_audit": [],
        "repos": [
            {"name": "web", "ecosystems": ["python"], "description": "web app", "markers": ["entry"]},
            {"name": "api", "ecosystems": ["python"], "description": "api", "markers": []},
            {"name": "core", "ecosystems": ["python"], "description": "core", "markers": []},
            {"name": "lib", "ecosystems": ["python"], "description": "lib", "markers": ["published"]},
        ],
        "warnings": [],
    }


def cyclic_pack():
    """a -> b -> a (a cycle): forces a back-edge."""
    return {
        "roles": {"a": ["hub"], "b": ["library"]},
        "relations": [_edge("a", "b"), _edge("b", "a")],
        "salience": {
            "a": {"in_degree": 1, "out_degree": 1, "hub": True},
            "b": {"in_degree": 1, "out_degree": 1, "hub": False},
        },
        "salience_audit": [],
        "repos": [
            {"name": "a", "ecosystems": ["python"], "description": "", "markers": []},
            {"name": "b", "ecosystems": ["python"], "description": "", "markers": []},
        ],
        "warnings": [],
    }
