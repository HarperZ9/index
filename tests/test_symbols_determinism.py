"""The symbol graph and its seal are byte-identical across runs."""
from index_graph.certify import canonical_sha
from index_graph.symbols import build_symbol_graph, symbol_graph_to_payload

from symbol_fixtures import write


def _busy(root):
    write(root, "lib.py", "def exported():\n    pass\n\n\ndef other():\n    exported()\n")
    write(root, "app.py",
          "from lib import exported\n\n\n"
          "class Runner:\n"
          "    def run(self):\n"
          "        self.step()\n"
          "        exported()\n"
          "    def step(self):\n"
          "        missing()\n")
    return root


def test_symbol_graph_is_byte_stable(tmp_path):
    _busy(tmp_path)
    g1 = build_symbol_graph(tmp_path)
    g2 = build_symbol_graph(tmp_path)
    assert canonical_sha(symbol_graph_to_payload(g1)) == canonical_sha(symbol_graph_to_payload(g2))


def test_symbols_are_sorted(tmp_path):
    _busy(tmp_path)
    g = build_symbol_graph(tmp_path)
    assert list(g.symbols) == sorted(g.symbols, key=lambda s: s.id)


def test_calls_are_sorted(tmp_path):
    _busy(tmp_path)
    g = build_symbol_graph(tmp_path)
    key = lambda c: (c.from_symbol, c.to_symbol or "", c.to_name,
                     c.evidence_file, c.evidence_line)
    assert list(g.calls) == sorted(g.calls, key=key)
