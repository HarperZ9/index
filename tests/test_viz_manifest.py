import hashlib

from workspace_repo_map.viz.manifest import render_manifest
from viz_fixtures import simple_pack


def _artifacts():
    return {
        "mermaid": ("graph.mmd", b"flowchart TD\n"),
        "svg": ("graph.svg", b"<svg></svg>"),
        "html": ("graph.html", b"<!doctype html>"),
        "context": ("context.json", b"{}"),
    }


def test_schema_and_counts():
    m = render_manifest(simple_pack(), artifacts=_artifacts(), meta={"version": "0.4.0", "commit": "abc", "root": "/r"})
    assert m["schema_version"] == "1"
    assert m["graph"]["node_count"] == 4
    assert m["graph"]["edge_count"] == 4
    assert m["receipts"] == {"present": False}
    assert m["generated"]["version"] == "0.4.0"


def test_hashes_match_artifact_bytes():
    arts = _artifacts()
    m = render_manifest(simple_pack(), artifacts=arts, meta={"version": "0.4.0", "commit": "abc", "root": "/r"})
    assert m["renders"]["svg"]["sha256"] == hashlib.sha256(arts["svg"][1]).hexdigest()
    assert m["renders"]["svg"]["path"] == "graph.svg"
    assert m["context_pack"]["sha256"] == hashlib.sha256(arts["context"][1]).hexdigest()
