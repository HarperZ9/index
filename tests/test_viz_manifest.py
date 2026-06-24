import hashlib
import json

from index_graph.viz.manifest import render_manifest
from viz_fixtures import simple_pack


def _artifacts():
    return {
        "mermaid": ("graph.mmd", b"flowchart TD\n"),
        "svg": ("graph.svg", b"<svg></svg>"),
        "html": ("graph.html", b"<!doctype html>"),
        "context": ("context.json", b"{}"),
    }


def test_schema_and_counts():
    m = render_manifest(simple_pack(), artifacts=_artifacts(), meta={"version": "1.0.0", "commit": "abc", "root": "/r"})
    assert m["schema_version"] == "1"
    assert m["graph"]["node_count"] == 4
    assert m["graph"]["edge_count"] == 4
    assert m["receipts"] == {"present": False}
    assert m["generated"]["version"] == "1.0.0"


def test_hashes_match_artifact_bytes():
    arts = _artifacts()
    m = render_manifest(simple_pack(), artifacts=arts, meta={"version": "1.0.0", "commit": "abc", "root": "/r"})
    assert m["renders"]["svg"]["sha256"] == hashlib.sha256(arts["svg"][1]).hexdigest()
    assert m["renders"]["svg"]["path"] == "graph.svg"
    assert m["renders"]["mermaid"]["sha256"] == hashlib.sha256(arts["mermaid"][1]).hexdigest()
    assert m["renders"]["mermaid"]["path"] == "graph.mmd"
    assert m["renders"]["html"]["sha256"] == hashlib.sha256(arts["html"][1]).hexdigest()
    assert m["renders"]["html"]["path"] == "graph.html"
    assert m["context_pack"]["sha256"] == hashlib.sha256(arts["context"][1]).hexdigest()


def test_snapshot_sha256_is_canonical_hash_of_pack():
    pack = simple_pack()
    m = render_manifest(pack, artifacts=_artifacts(), meta={"version": "1.0.0", "commit": "abc", "root": "/r"})
    expected = hashlib.sha256(json.dumps(pack, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert m["graph"]["snapshot_sha256"] == expected
