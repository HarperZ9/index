"""Tests for the token-economy benchmark (index bench)."""
import json

from index_graph.bench import SCHEMA, bench_workspace
from index_graph.cli import main


def _repo(d, name, dep=None, body_files=3):
    (d / ".git").mkdir(parents=True, exist_ok=True)
    deps = f'["{dep}"]' if dep else "[]"
    (d / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\ndependencies = {deps}\n', encoding="utf-8")
    (d / "main.py").write_text(
        ("import %s\n" % dep if dep else "") + "def f():\n    return 1\n" * 40, encoding="utf-8")
    for i in range(body_files):
        (d / f"mod{i}.py").write_text("x = 1\n" * 60, encoding="utf-8")
    return d


def test_bench_report_shape(tmp_path):
    _repo(tmp_path / "app", "app", dep="lib")
    _repo(tmp_path / "lib", "lib")
    rep = bench_workspace({"app": tmp_path / "app", "lib": tmp_path / "lib"})
    assert rep["schema"] == SCHEMA
    assert rep["repos"] == 2
    assert rep["source_bytes"] > 0 and rep["pack_bytes"] > 0
    assert rep["source_files"] >= 8  # 2 manifests + 2 main.py + 6 mod*.py
    assert rep["approx_tokens_source"] == rep["source_bytes"] // rep["bytes_per_token"]


def test_bench_reduction_gt_one_for_real_source(tmp_path):
    # plenty of source: the structural pack must be smaller than the code it distills
    _repo(tmp_path / "app", "app", dep="lib", body_files=6)
    _repo(tmp_path / "lib", "lib", body_files=6)
    rep = bench_workspace({"app": tmp_path / "app", "lib": tmp_path / "lib"})
    assert rep["reduction"] > 1.0
    assert rep["reduction"] == round(rep["source_bytes"] / rep["pack_bytes"], 1)


def test_bench_is_deterministic(tmp_path):
    _repo(tmp_path / "app", "app")
    paths = {"app": tmp_path / "app"}
    assert bench_workspace(paths) == bench_workspace(paths)


def test_bench_cli_json(tmp_path, capsys):
    _repo(tmp_path / "app", "app", dep="lib")
    _repo(tmp_path / "lib", "lib")
    rc = main(["bench", "--root", str(tmp_path), "--json"])
    assert rc == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["schema"] == SCHEMA
    assert rep["reduction"] > 1.0
    assert rep["recheck"].startswith("index bench")


def test_bench_cli_json_uses_workspace_cache(tmp_path, capsys, monkeypatch):
    _repo(tmp_path / "app", "app", dep="lib")
    _repo(tmp_path / "lib", "lib")
    monkeypatch.setenv("INDEX_CACHE_DIR", str(tmp_path.parent / f"{tmp_path.name}-cache"))
    monkeypatch.setenv("INDEX_CACHE_TTL_SECONDS", "900")

    assert main(["bench", "--root", str(tmp_path), "--json"]) == 0
    first = json.loads(capsys.readouterr().out)

    import index_graph.bench as bench_pkg

    def fail_if_cache_misses(_paths, **_kwargs):
        raise AssertionError("bench cache miss")

    monkeypatch.setattr(bench_pkg, "bench_workspace", fail_if_cache_misses)
    assert main(["bench", "--root", str(tmp_path), "--json"]) == 0
    second = json.loads(capsys.readouterr().out)

    assert second == first


def test_bench_cli_human(tmp_path, capsys):
    _repo(tmp_path / "app", "app")
    rc = main(["bench", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "token economy" in out
    assert "x smaller" in out


def test_faithfulness_every_kept_edge_is_grounded_in_source(tmp_path):
    # the honesty dimension: a byte reduction is only real if it fabricates
    # nothing. Every internal dependency edge index keeps must cite the import
    # that produced it (file:line evidence) -> grounding 1.0.
    _repo(tmp_path / "app", "app", dep="lib")
    _repo(tmp_path / "lib", "lib")
    rep = bench_workspace({"app": tmp_path / "app", "lib": tmp_path / "lib"})
    f = rep["faithfulness"]
    assert f["internal_edges"] >= 1                 # app -> lib is a real edge
    assert f["grounded_edges"] == f["internal_edges"]
    assert f["edge_grounding"] == 1.0               # the reduction invented no structure


def test_faithfulness_in_cli_human_output(tmp_path, capsys):
    _repo(tmp_path / "app", "app", dep="lib")
    _repo(tmp_path / "lib", "lib")
    assert main(["bench", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "faithfulness" in out and "grounded in file:line" in out


def test_edge_grounding_is_null_on_a_workspace_with_no_internal_edges(tmp_path):
    # a single repo with no internal dependency edges grounded nothing: the
    # faithfulness must be an honest null, not a vacuous 1.0
    _repo(tmp_path / "solo", "solo")
    rep = bench_workspace({"solo": tmp_path / "solo"})
    f = rep["faithfulness"]
    assert f["internal_edges"] == 0
    assert f["edge_grounding"] is None
