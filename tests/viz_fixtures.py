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


def simple_atlas():
    """2 repos (app -> lib) + 3 docs. app/README describes app, lib/README describes lib,
    docs/arch.md is cross-cutting. Exercises describes / links-to / mentions."""
    from index_graph.knowledge.docs import Doc
    pack = {
        "roles": {"app": ["entrypoint"], "lib": ["library"]},
        "relations": [_edge("app", "lib")],
        "cycles": [],
        "salience": {
            "app": {"in_degree": 0, "out_degree": 1, "hub": False},
            "lib": {"in_degree": 1, "out_degree": 0, "hub": False},
        },
        "salience_audit": [],
        "repos": [
            {"name": "app", "ecosystems": ["python"], "description": "app", "markers": ["entry"]},
            {"name": "lib", "ecosystems": ["python"], "description": "lib", "markers": ["published"]},
        ],
        "warnings": [],
        "docs": [
            {"id": "app/README.md", "title": "App", "dir": "app"},
            {"id": "docs/arch.md", "title": "Architecture", "dir": "docs"},
            {"id": "lib/README.md", "title": "Lib", "dir": "lib"},
        ],
        "knowledge_edges": [
            {"type": "describes", "from": "app/README.md", "to": "app", "to_kind": "repo"},
            {"type": "links-to", "from": "app/README.md", "to": "lib", "to_kind": "repo"},
            {"type": "links-to", "from": "docs/arch.md", "to": "app", "to_kind": "repo"},
            {"type": "describes", "from": "lib/README.md", "to": "lib", "to_kind": "repo"},
            {"type": "mentions", "from": "docs/arch.md", "to": "lib", "to_kind": "repo"},
        ],
        "knowledge_warnings": [],
    }
    docs = [
        Doc("app/README.md", "App", "# App\n\nThe app. Uses [[lib]].", ("lib",), "app"),
        Doc("docs/arch.md", "Architecture", "# Architecture\n\nApp and lib. See [[App]].", ("app",), "docs"),
        Doc("lib/README.md", "Lib", "# Lib\n\nThe library.", (), "lib"),
    ]
    return pack, docs


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
