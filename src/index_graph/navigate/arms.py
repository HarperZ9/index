"""Search arms compared against the navigator, all over the same outline.

Every arm returns the same shape: the first ``k`` distinct files it ranks and
the tokens of the context it would hand to a model. Leaf arms deliver leaves
in rank order until ``k`` distinct files are covered, the same rule the
navigator uses, so token counts compare like for like.
"""
from __future__ import annotations

from .chooser import Chooser
from .maps import Map, MapEntry
from .outline import Node, Outline
from .text import BM25, approx_tokens, tokens
from .walk import first_per_file, navigate


def deliver_leaves(ranked: list[Node], k: int) -> dict:
    """Take leaves in order until ``k`` distinct files are covered."""
    files: list[str] = []
    taken: list[Node] = []
    for leaf in ranked:
        if leaf.file not in files:
            if len(files) == k:
                break
            files.append(leaf.file)
        taken.append(leaf)
    return {"files": files, "tokens_shown": sum(approx_tokens(n.text) for n in taken),
            "question_tokens": 0, "leaves": [n.id for n in taken]}


def bm25_chunk_best_arm(outline: Outline, query: str, k: int = 5) -> dict:
    """BM25 over leaves, delivering only the best leaf of each of the top ``k`` files."""
    index = BM25(tokens(leaf.text) for leaf in outline.leaves)
    ranked = first_per_file([outline.leaves[i] for i, _ in index.rank(tokens(query))])
    return deliver_leaves(ranked, k)


def grep_arm(outline: Outline, query: str, k: int = 5) -> dict:
    """Files ranked by how many distinct query terms they contain; deliver matching lines."""
    terms = set(tokens(query))
    rows = []
    for rel, text in outline.files.items():
        hits, matched = [], set()
        for number, line in enumerate(text.splitlines(), 1):
            found = terms.intersection(tokens(line))
            if found:
                matched |= found
                hits.append(f"{rel}:{number}:{line}")
        if matched:
            rows.append((-len(matched), -len(hits), rel, hits))
    rows.sort()
    top = rows[:k]
    return {"files": [r[2] for r in top],
            "tokens_shown": sum(approx_tokens("\n".join(r[3])) for r in top),
            "question_tokens": 0}


def bm25_file_arm(outline: Outline, query: str, k: int = 5) -> dict:
    """BM25 over whole files; deliver the full text of the top ``k`` files."""
    paths = sorted(outline.files)
    index = BM25(tokens(outline.files[p]) for p in paths)
    top = [paths[i] for i, _ in index.rank(tokens(query))[:k]]
    return {"files": top, "tokens_shown": sum(approx_tokens(outline.files[p]) for p in top),
            "question_tokens": 0}


def bm25_chunk_arm(outline: Outline, query: str, k: int = 5) -> dict:
    """BM25 over leaf source text; deliver leaves until ``k`` files are covered."""
    index = BM25(tokens(leaf.text) for leaf in outline.leaves)
    ranked = [outline.leaves[i] for i, _ in index.rank(tokens(query))]
    return deliver_leaves(ranked, k)


def map_arm(outline: Outline, query: str, chooser: Chooser, k: int = 5) -> dict:
    """One flat map of every leaf; the chooser scores all entries in a single question."""
    flat = Map([MapEntry(name=leaf.id, description=leaf.description, handle=leaf)
                for leaf in outline.leaves])
    dist = chooser.choose(query, flat)
    order = sorted(range(len(dist)), key=lambda i: (-dist[i], i))
    ranked = [flat.entries[i].handle for i in order if dist[i] > 0]
    result = deliver_leaves(ranked, k)
    result["question_tokens"] = approx_tokens(query) + sum(
        approx_tokens(e["name"] + " " + e["description"]) for e in flat.for_model())
    return result


def navigate_arm(outline: Outline, query: str, chooser: Chooser, k: int = 5, **kw) -> dict:
    result = navigate(outline, query, chooser, max_files=k, **kw)
    return {"files": result["files"], "tokens_shown": result["tokens_shown"],
            "question_tokens": result["question_tokens"],
            "leaves": [leaf["id"] for leaf in result["leaves"]]}
