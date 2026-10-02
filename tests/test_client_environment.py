"""The client profile never reads a credential from the environment, even in a Git workspace."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACER = r'''
import json, os, sys
from pathlib import Path
seen, iterated = set(), []
cls = type(os.environ)
for name in ("__getitem__", "get", "__contains__"):
    def wrap(orig):
        def method(self, key, *rest):
            seen.add(key)
            return orig(self, key, *rest)
        return method
    setattr(cls, name, wrap(getattr(cls, name)))
original_iter = cls.__iter__
def tracked_iter(self):
    iterated.append(True)
    return original_iter(self)
cls.__iter__ = tracked_iter
sys.path.insert(0, sys.argv[1])
from index_graph.client_mcp import main
code = main(sys.argv[2:])
sys.stderr.write("TRACE " + json.dumps({"seen": sorted(seen), "iterated": bool(iterated)}) + "\n")
raise SystemExit(code)
'''


def test_git_workspace_map_never_reads_or_copies_the_environment(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / ".git").mkdir(parents=True)
    (workspace / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (workspace / "mod.py").write_text("def parse_config(x):\n    return x\n", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    tracer = tmp_path / "tracer.py"
    tracer.write_text(TRACER, encoding="utf-8")
    env = {**os.environ, "PLANTED_TEST_TOKEN": "planted-secret-value"}
    calls = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}
             for i, (name, args) in enumerate([
                 ("index.map", {"root": "."}), ("index.map", {"root": "."}),
                 ("index.select", {"root": "."}), ("index.symbol-graph", {"root": "."}),
                 ("index.symbol-definition", {"root": ".", "symbol": "parse_config"}),
                 ("index.symbol-references", {"root": ".", "symbol": "parse_config"}),
                 ("index.symbol-implementations", {"root": ".", "symbol": "parse_config"})], 1)]
    wire = "".join(json.dumps(c) + "\n" for c in calls)
    for extra in ([], ["--state-directory", str(state)]):
        result = subprocess.run([sys.executable, "-I", "-S", "-B", str(tracer),
                                 str(ROOT / "client-plugin/server/src"), "--workspace", str(workspace), *extra],
                                input=wire, capture_output=True, text=True, env=env, timeout=30, check=False)
        assert result.returncode == 0, result.stderr
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(rows) == len(calls) and not any(r["result"]["isError"] for r in rows), rows
        mapped = json.loads(rows[0]["result"]["content"][0]["text"])
        assert mapped["repo_count"] == 1 and mapped["metadata_unknown_count"] == 1
        trace = json.loads(result.stderr.split("TRACE ", 1)[1])
        assert trace["iterated"] is False
        assert "PLANTED_TEST_TOKEN" not in trace["seen"]
        assert not any(k.startswith("GIT") or k == "INDEX_GIT_TIMEOUT_SECONDS" for k in trace["seen"]), trace
        assert "planted-secret-value" not in result.stdout + result.stderr
        assert "does not grant processes" not in result.stderr
