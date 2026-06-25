import pytest

from index_graph.certify import canonical_sha, build_certificate


def test_canonical_sha_is_order_independent():
    assert canonical_sha({"a": 1, "b": 2}) == canonical_sha({"b": 2, "a": 1})


def test_certificate_shape_and_recheck_roundtrip():
    content = {"edges": ["a -> b"]}
    cert = build_certificate("check", content=content, criterion={"layers": ["core"]},
                             verdict="MATCH", findings=[], recheck="index check --root .",
                             tool_version="2.0.0")
    assert cert["schema"] == "index.certificate/1"
    assert cert["kind"] == "check"
    assert cert["verdict"] == "MATCH"
    assert cert["tool_version"] == "2.0.0"
    assert cert["content_sha256"] == canonical_sha(content)
    assert cert["criterion_sha256"] == canonical_sha({"layers": ["core"]})
    assert cert["recheck"] == "index check --root ."


def test_no_criterion_means_null_hash():
    cert = build_certificate("drift", content={"x": 1}, criterion=None,
                             verdict="DRIFT", findings=[], recheck="index drift ...",
                             tool_version="2.0.0")
    assert cert["criterion_sha256"] is None


def test_fourth_verdict_rejected():
    with pytest.raises(ValueError):
        build_certificate("check", content={}, criterion=None, verdict="TRUSTED",
                          findings=[], recheck="x", tool_version="2.0.0")
