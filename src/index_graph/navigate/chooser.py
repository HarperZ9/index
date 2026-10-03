"""Choosers answer one typed question: which of these map entries fits the query?

The answer is a probability distribution over the entries, never free text, so
the navigator can branch on it and the decision path can record it. The
default chooser is lexical and runs locally with no model. A model-backed
chooser plugs in through the same ``choose`` signature.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Protocol

from .maps import Map
from .text import tokens

FLAT_EPSILON = 1e-9


class Chooser(Protocol):
    name: str

    def choose(self, query: str, options: Map) -> list[float]:
        """A distribution aligned with ``options.entries``; sums to 1."""
        ...


def softmax(scores: list[float], temperature: float) -> list[float]:
    if not scores:
        return []
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    top = max(scores)
    weights = [math.exp((s - top) / temperature) for s in scores]
    total = sum(weights)
    return [w / total for w in weights]


def is_flat(dist: list[float]) -> bool:
    """True when the chooser could not tell the options apart."""
    return len(dist) > 1 and max(dist) - min(dist) < FLAT_EPSILON


class LexicalChooser:
    """BM25-style overlap between the query and each entry's description.

    ``idf`` comes from the whole outline, so a rare term counts for more at
    every level. Scores become probabilities through a softmax at
    ``temperature``; lower values make the chooser more decisive.
    """

    name = "lexical"

    def __init__(self, idf: dict[str, float], temperature: float = 0.3,
                 k1: float = 1.2, b: float = 0.5):
        self.idf, self.temperature, self.k1, self.b = idf, temperature, k1, b

    def scores(self, query: str, options: Map) -> list[float]:
        terms = set(tokens(query))
        bags = [Counter(tokens(e.description)) for e in options.entries]
        lengths = [sum(b.values()) for b in bags]
        avg = (sum(lengths) / len(lengths)) if lengths else 1.0
        out = []
        for bag, length in zip(bags, lengths):
            norm = self.k1 * (1 - self.b + self.b * length / (avg or 1.0))
            out.append(sum(self.idf.get(t, 0.0) * bag[t] * (self.k1 + 1) / (bag[t] + norm)
                           for t in terms if bag.get(t)))
        return out

    def choose(self, query: str, options: Map) -> list[float]:
        """Scores scaled by the best option's score, then a softmax at ``temperature``.

        Scaling makes the temperature mean the same thing at every level: at
        0.3, an option needs about 79% of the top score to stay within half
        the top probability.
        """
        raw = self.scores(query, options)
        top = max(raw, default=0.0)
        return softmax([s / top for s in raw] if top > 0 else raw, self.temperature)
