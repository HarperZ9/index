"""A local binding that shadows a module-level def must not mint a false
exact/high call edge to the module symbol. Shadowing is a guess dressed as
certainty; the map must not assert a call the code does not have."""
from index_graph.symbols import build_symbol_graph

from symbol_fixtures import write


def test_parameter_shadowing_a_module_def_is_not_a_resolved_edge(tmp_path):
    write(tmp_path, "mod.py",
          "def handler():\n"
          "    pass\n\n"
          "def run(handler):\n"
          "    handler()\n")
    g = build_symbol_graph(tmp_path)
    run = next(s for s in g.symbols if s.name == "run")
    # the call on the local `handler` parameter must NOT resolve to mod::handler
    to_module = [c for c in g.calls
                 if c.from_symbol == run.id and c.to_symbol == "mod::handler"]
    assert to_module == [], "a shadowing parameter minted a false exact edge"


def test_for_loop_target_shadowing_is_not_a_resolved_edge(tmp_path):
    write(tmp_path, "mod.py",
          "def handler():\n"
          "    pass\n\n"
          "def run(items):\n"
          "    for handler in items:\n"
          "        handler()\n")
    g = build_symbol_graph(tmp_path)
    run = next(s for s in g.symbols if s.name == "run")
    to_module = [c for c in g.calls
                 if c.from_symbol == run.id and c.to_symbol == "mod::handler"]
    assert to_module == [], "a shadowing for-target minted a false exact edge"


def test_a_genuine_module_call_still_resolves(tmp_path):
    # the fix must not suppress a real edge: no shadowing here
    write(tmp_path, "mod.py",
          "def handler():\n"
          "    pass\n\n"
          "def run():\n"
          "    handler()\n")
    g = build_symbol_graph(tmp_path)
    run = next(s for s in g.symbols if s.name == "run")
    real = [c for c in g.calls
            if c.from_symbol == run.id and c.to_symbol == "mod::handler"]
    assert len(real) == 1 and real[0].resolution == "exact"
