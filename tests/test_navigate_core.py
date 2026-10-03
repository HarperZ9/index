"""Maps, choosers, leaf spans and scoring for `index navigate`.

Each behaviour check is a function run twice: against the real code, where it
must pass, and against a named mutant, where it must fail. A check that cannot
tell the mutant apart asserts nothing.
"""
from __future__ import annotations

import pytest

from index_graph.navigate import bench, chooser as chooser_mod, walk
from index_graph.navigate.maps import Map, MapEntry
from index_graph.navigate.pysource import python_spans

SOURCE = '''"""Doc."""
import os

X = 1


@decorator
def alpha(a, b):
    return os.path.join(a, b)


class Beta(Base):
    """A class."""
    size = 3

    def one(self):
        return 1

    def two(self):
        return 2

Y = 2
'''


def check_partition(spans_fn) -> None:
    """Every source line belongs to exactly one leaf: the leaf texts hold each line once."""
    spans, _ = spans_fn(SOURCE)
    pieces = [line for span in spans for line in span[5].split("\n")]
    assert sorted(pieces) == sorted(SOURCE.rstrip("\n").split("\n"))
    assert sum(len(span[5].split("\n")) for span in spans) == SOURCE.count("\n")


def test_python_leaves_partition_the_file():
    check_partition(python_spans)


def test_partition_check_catches_a_dropped_module_block():
    def mutant(text):
        spans, doc = python_spans(text)
        return [s for s in spans if s[0] != "module"], doc
    with pytest.raises(AssertionError):
        check_partition(mutant)


def test_leaf_kinds_and_decorator_start():
    spans, doc = python_spans(SOURCE)
    by_name = {s[1]: s for s in spans}
    assert doc == "Doc."
    assert by_name["alpha"][2] == 7, "a decorated function starts at its decorator"
    assert by_name["Beta"][0] == "class" and "one two" in by_name["Beta"][4]
    assert by_name["Beta.one"][0] == "method"
    assert by_name["<module>"][5].splitlines()[1] == "import os"
    assert python_spans("def broken(:\n") is None


def check_map_hides_handles(map_cls) -> None:
    m = map_cls([MapEntry("a", "first", {"secret": 1}), MapEntry("b", "second", 2)])
    assert m.for_model() == [{"name": "a", "description": "first"},
                             {"name": "b", "description": "second"}]
    assert m.resolve("b") == 2
    with pytest.raises(KeyError):
        m.resolve("c")


def test_map_shows_names_and_descriptions_only():
    check_map_hides_handles(Map)
    with pytest.raises(ValueError, match="unique"):
        Map([MapEntry("a", "x", 1), MapEntry("a", "y", 2)])


def test_map_check_catches_a_handle_leak():
    class Leaky(Map):
        def for_model(self):
            return [{"name": e.name, "description": e.description, "handle": e.handle}
                    for e in self.entries]
    with pytest.raises(AssertionError):
        check_map_hides_handles(Leaky)


def check_follow(follow) -> None:
    dist = [0.40, 0.20, 0.19, 0.21]
    assert follow(dist, 0.5, 4) == [0, 3, 1], "half the top (0.20) is included, 0.19 is not"
    assert follow(dist, 0.5, 2) == [0, 3], "the beam caps the followed children"
    assert follow([], 0.5, 4) == []


def test_follow_applies_the_half_of_top_rule_and_beam():
    check_follow(walk.follow)


@pytest.mark.parametrize("mutant", [
    lambda d, r, b: [i for i, p in enumerate(d) if p > r * max(d)][:b],   # strict >
    lambda d, r, b: sorted(range(len(d)), key=lambda i: -d[i])[:b] if d else [],  # no ratio
    lambda d, r, b: sorted((i for i, p in enumerate(d) if p >= r * max(d)),
                           key=lambda i: -d[i]) if d else [],  # no beam
])
def test_follow_check_catches_mutants(mutant):
    with pytest.raises(AssertionError):
        check_follow(mutant)


def test_lexical_chooser_is_scaled_and_reports_flat():
    idf = {"retry": 2.0, "cache": 2.0}
    options = Map([MapEntry("r", "retry retry", 0), MapEntry("c", "cache", 1),
                   MapEntry("n", "nothing", 2)])
    choose = chooser_mod.LexicalChooser(idf, temperature=0.3).choose
    dist = choose("retry", options)
    assert abs(sum(dist) - 1) < 1e-9 and dist[0] > 0.9
    assert chooser_mod.is_flat(choose("unrelated words", options))
    with pytest.raises(ValueError):
        chooser_mod.softmax([1.0], 0)


def check_recall(recall) -> None:
    assert recall(["a", "a", "b", "c", "d", "f"], ["f"], k=5) == 1.0, "duplicates do not use slots"
    assert recall(["a", "b"], ["a", "z"], k=5) == 0.5
    assert recall(["x", "y", "z", "w", "v", "a"], ["a"], k=5) == 0.0


def test_recall_dedupes_and_cuts_at_k():
    check_recall(bench.recall_at_k)


def test_recall_check_catches_no_dedupe():
    def mutant(ranked, answer, k=5):
        return len(set(ranked[:k]) & set(answer)) / len(set(answer))
    with pytest.raises(AssertionError):
        check_recall(mutant)


def _rows(nav, other, nav_tok, other_tok, third_tok):
    return [{"navigate": {"recall": n, "tokens_shown": nav_tok},
             "a": {"recall": o, "tokens_shown": other_tok},
             "b": {"recall": o, "tokens_shown": third_tok}} for n, o in zip(nav, other)]


def test_verdict_picks_the_cheaper_of_tied_arms_and_applies_both_bars():
    rows = _rows([1, 1, 0, 1], [1, 1, 1, 0], 10, 100, 30)
    v = bench.verdict(rows, ["a", "b", "navigate"])
    assert v["best_arm"] == "b", "a recall tie breaks toward fewer tokens"
    assert v["token_ratio"]["ratio"] == pytest.approx(10 / 30)
    assert v["primary_pass"] and not v["strong_pass"]
    worse = bench.verdict(_rows([0, 0, 0, 1], [1, 1, 1, 0], 10, 100, 30), ["a", "b", "navigate"])
    assert not worse["primary_pass"]


def test_bootstrap_is_seeded_and_brackets_the_mean():
    a, b = [1, 0, 1, 1, 0, 1], [0, 0, 1, 0, 0, 1]
    first, second = bench.paired_bootstrap(a, b), bench.paired_bootstrap(a, b)
    assert first == second
    assert first["low"] <= first["mean"] <= first["high"]
    with pytest.raises(ValueError):
        bench.paired_bootstrap([1], [1, 2])
