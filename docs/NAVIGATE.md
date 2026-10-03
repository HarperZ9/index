# Navigate: find the code for a question

`index navigate` takes a question in plain words and returns the few pieces of code that answer it. It walks the repository the way a person skims an unfamiliar codebase: pick the likely directories, then the likely files, then the likely functions. At each step it answers one small question, and only the pieces it lands on reach your context window.

```bash
index navigate . "path selection with typed rejection receipts"
index navigate . "path selection with typed rejection receipts" --json   # adds source text and the decision path
```

Run on this repository, which keeps a copy of its server code inside the client plugin folder:

```text
navigate files=5 questions=15 tokens_shown=1336
  client-plugin/server/src/index_graph/context/select.py:1-231  <module>  p=0.314
  src/index_graph/context/select.py:1-231  <module>  p=0.312
  src/index_graph/route.py:81-98  _empty_receipt  p=0.188
  client-plugin/server/src/index_graph/route.py:81-98  _empty_receipt  p=0.186
  tests/test_select.py:1-206  <module>  p=0.056
```

Each line names a file, a line span and a leaf, so you can open the exact spot. A `<module>` leaf holds the file's lines outside any function or class, such as imports and constants. The probability says how confident the walk was in that branch.

## How it works

1. **The outline.** The repository becomes a tree: directories, files, then the functions, methods, class headers and module-level code inside each Python file. Other code files split into 80-line blocks. Each inner node carries a short description: its name, its children's names, and the most distinctive terms beneath it.
2. **One typed question per level.** At each node the chooser sees only that node's children, offered as a map, and returns a probability for each child. The default chooser is lexical and runs locally with no model.
3. **Branch on the answer.** Every child at least half as likely as the top child is followed, up to four per node. Children not followed wait in a backlog, used only when the followed branches run out before enough files turn up.
4. **Only leaves reach you.** The walk stops after five files by default and delivers the best leaf of each one. `--all-leaves` delivers every leaf reached.
5. **The path is the receipt.** `--json` includes every question asked, the distribution returned and the children followed, so anyone can replay the walk offline.

Code files only by default. `--include-docs` adds prose and config files.

## Maps: let your own model choose

A map is a list of names, each with a description for a model and a handle for the code. The model points at a name; the code resolves the name to a real node. A model can only choose among things that exist.

```bash
index outline-map .                                    # the root's children
index outline-map . --node src/index_graph/navigate/      # one level down, using a handle from the last map
index outline-map . --node src/index_graph/navigate/walk.py::follow --json   # a leaf returns its source
```

Over MCP, `index.outline-map` gives an agent host the same walk with its own model as the chooser, and `index.navigate` runs the built-in walk in one call. Both tools are in the full server and in the read-only client plugin.

## Benchmark

We froze 60 questions before measuring: the titles of merged pull requests in three of our repositories (index 26, gather 20, crucible 14), each answered against the repository as it stood before the change. The answer is the set of Python files the pull request modified, tests excluded. The query file's SHA-256 is `a264681f55123d9bdd62a07446eb1a70d61f9ed02e2c9d696ee5bed3118eaade`. Settings were tuned only on a separate 16-question design set from a fourth repository.

Recall@5 is the share of answer files among the first five files an arm returns. Tokens shown are the bytes handed to a model, divided by four. Intervals are 95% paired bootstrap over questions (10,000 resamples, seed 20261003).

| Arm | What it hands over | Recall@5 | Tokens shown (60 questions) |
|:--|:--|--:|--:|
| grep | matching lines of the top 5 files | 0.422 | 197,857 |
| BM25, whole files | full text of the top 5 files | 0.410 | 536,785 |
| BM25, symbol chunks | chunks until 5 files | 0.289 | 99,098 |
| BM25, best chunk per file | one chunk from each of 5 files | 0.289 | 59,623 |
| flat map | leaves until 5 files, one question over every symbol | 0.373 | 106,541 |
| **navigate** | best leaf of each of 5 files | **0.389** | **65,472** |

The bar, written before the run: navigate's recall within 0.05 of the best other arm, at no more than half its tokens.

- Against grep, the best other arm: recall difference -0.033 (interval -0.114 to 0.055), token ratio 0.33 (interval 0.27 to 0.41). The bar passes on the point estimates. The stricter version, which also asks the recall interval to stay above -0.05, does not pass: with 60 questions, a drop of up to 0.11 is not ruled out.
- Against BM25 with the same delivery unit (best chunk per file): recall +0.100 (interval 0.011 to 0.196) at a token ratio of 1.10 (interval 0.91 to 1.31).
- Per repository, recall varied: index 0.48 (grep 0.50), gather 0.39 (grep 0.36), crucible 0.21 (grep 0.37).

On the design set, the same settings fell short: navigate 0.521 against grep 0.641. The held-out result is the test; the design result is a reminder that 60 questions leave wide intervals.

The built-in chooser reads about 41,000 tokens of descriptions per question on these repositories. That costs nothing with the local lexical chooser. With a model as the chooser, through `index.outline-map`, those reads would cost model calls, and this benchmark did not measure that setup.

Reproduce with the files in [`benchmarks/navigate/`](../benchmarks/navigate/):

```bash
python benchmarks/navigate/build_queries.py --repos-root ..   # rebuilds both query files byte for byte
python scripts/navigate_bench.py --queries benchmarks/navigate/queries-heldout-v1.json \
    --repos-root .. --cache .navigate-cache --out results.json
```

## Limits

- Pull request titles are an easy, noisy stand-in for real questions, and answer sets include incidental edits. File recall says nothing about whether a coding task then succeeds.
- The chooser is lexical. A class header's description lists its method names, so a question about one method can land on the class header first; the file is still right.
- Only Python files get symbol-level leaves today.
