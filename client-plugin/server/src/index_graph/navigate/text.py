"""Shared tokenizer and BM25 scorer for every navigation and search arm.

One tokenizer and one stop list serve all arms, so a recall difference between
arms comes from what each arm looks at, never from how it splits words.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")

STOP = frozenset("""
a an and are as at be but by for from has have in into is it its not of on or
that the their them then there these this to was were will with without when
which who why how what so do does done can could should would may might must
than too very own same each every any all both only also just over under out
up down off our we you your he she they i me my no nor if else while about
after before again further once here more most other some such self none true
false return def class import none str int dict list
""".split())


def split_identifier(word: str) -> list[str]:
    """Split ``parseHTTPResponse`` or ``parse_http`` into lower-case parts."""
    parts = [p.lower() for p in _CAMEL.findall(word)]
    return parts or [word.lower()]


def tokens(text: str) -> list[str]:
    """Lower-case content tokens: identifiers split, stop words and 1-letter words dropped.

    A compound identifier also keeps its whole lower-cased form, so
    ``build_graph`` matches both ``build graph`` and ``build_graph``.
    """
    out: list[str] = []
    for raw in _WORD.findall(text.replace("_", " _ ")):
        for part in split_identifier(raw):
            if len(part) > 1 and part not in STOP:
                out.append(_stem(part))
    for compound in re.findall(r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+", text):
        out.append(compound.lower())
    return out


def _stem(word: str) -> str:
    """A tiny suffix stripper: enough to join ``checks``/``check`` and ``loading``/``load``."""
    for suffix in ("ing", "ies", "es", "ed", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


class BM25:
    """Okapi BM25 over a fixed list of documents (k1=1.2, b=0.75)."""

    def __init__(self, docs: Iterable[list[str]], k1: float = 1.2, b: float = 0.75):
        self.docs = [Counter(d) for d in docs]
        self.lengths = [sum(c.values()) for c in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        self.k1, self.b = k1, b
        df: Counter = Counter()
        for counts in self.docs:
            df.update(counts.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: list[str], index: int) -> float:
        counts, length = self.docs[index], self.lengths[index]
        norm = self.k1 * (1 - self.b + self.b * length / self.avg) if self.avg else self.k1
        total = 0.0
        for term in set(query):
            tf = counts.get(term, 0)
            if tf:
                total += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / (tf + norm)
        return total

    def rank(self, query: list[str]) -> list[tuple[int, float]]:
        """Indexes with a positive score, best first; ties keep document order."""
        scored = [(i, self.score(query, i)) for i in range(len(self.docs))]
        return sorted((s for s in scored if s[1] > 0), key=lambda s: (-s[1], s[0]))


def approx_tokens(text: str) -> int:
    """Context cost of ``text``: UTF-8 bytes over 4, rounded up (the index.bench/1 rule)."""
    return -(-len(text.encode("utf-8")) // 4)
