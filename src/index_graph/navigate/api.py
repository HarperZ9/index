"""Shared payloads for the CLI and MCP faces of navigation and outline maps."""
from __future__ import annotations

from pathlib import Path

from .chooser import LexicalChooser
from .maps import Map
from .outline import Node, Outline, build_outline
from .walk import DEFAULT_BEAM, DEFAULT_RATIO, children_map, navigate

NAVIGATE_SCHEMA = "index.navigate/v1"
OUTLINE_MAP_SCHEMA = "index.outline-map/v1"


def _check_root(root: Path) -> Path:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"root not found: {root}")
    return root


def run_navigate(root: Path | str, query: str, *, max_files: int = 5,
                 beam: int = DEFAULT_BEAM, ratio: float = DEFAULT_RATIO,
                 temperature: float = 0.3, include_docs: bool = False,
                 all_leaves: bool = False, with_text: bool = True) -> dict:
    """Navigate ``root`` for ``query``; leaves carry their source text unless ``with_text`` is off."""
    query = (query or "").strip()
    if not query:
        raise ValueError("missing required argument: query")
    if max_files < 1 or beam < 1 or not 0 < ratio <= 1:
        raise ValueError("max_files and beam must be >= 1; ratio must be in (0, 1]")
    outline = build_outline(_check_root(root), include_docs=include_docs)
    chooser = LexicalChooser(outline.idf, temperature=temperature)
    result = navigate(outline, query, chooser, ratio=ratio, beam=beam,
                      max_files=max_files, all_leaves=all_leaves)
    nodes = result.pop("_leaf_nodes")
    if with_text:
        for leaf, node in zip(result["leaves"], nodes):
            leaf["text"] = node.text
    return {"schema": NAVIGATE_SCHEMA, **result}


def find_node(outline: Outline, node_id: str) -> Node:
    """The outline node with ``node_id`` ("" or "." is the root). Unknown ids raise."""
    wanted = "" if node_id in ("", ".") else node_id
    stack = [outline.root]
    while stack:
        node = stack.pop()
        if node.id == wanted:
            return node
        stack.extend(node.children)
    raise KeyError(f"no outline node: {node_id!r}")


def outline_map(root: Path | str, node: str = "", *, include_docs: bool = False) -> dict:
    """The children of one outline node as a map a model can point into.

    Each entry gives the model a name and a description; the handle is the
    child's node id, which the caller passes back as ``node`` to go one level
    down. A leaf has no children; its map is empty and its source is returned.
    """
    outline = build_outline(_check_root(root), include_docs=include_docs)
    target = find_node(outline, node)
    options: Map = children_map(target)
    payload = options.to_json(handle_view=lambda child: {
        "node": child.id, "kind": child.kind, "file": child.file,
        "start": child.start or None, "end": child.end or None})
    payload.update({"schema": OUTLINE_MAP_SCHEMA, "node": target.id or ".",
                    "kind": target.kind})
    if target.is_leaf:
        payload["text"] = target.text
    return payload


def tool_definitions(root_schema) -> list[dict]:
    """MCP definitions for `index.navigate` and `index.outline-map`."""
    return [
        {"name": "index.navigate",
         "description": "Find the code for a plain-language question by walking the repo one "
                        "level at a time (directory, file, symbol) with a typed choice per level. "
                        "Returns only the leaves reached, with source text, plus the decision path, "
                        "matching the `index navigate --json` CLI surface.",
         "inputSchema": root_schema({
             "query": {"type": "string", "description": "the question, in plain words"},
             "max_files": {"type": "integer", "description": "stop after this many files (5)"},
             "beam": {"type": "integer", "description": "most children followed per level (4)"},
             "ratio": {"type": "number", "description": "follow children at least this share "
                                                        "of the top child's probability (0.5)"},
             "include_docs": {"type": "boolean", "description": "also walk prose and config"},
             "all_leaves": {"type": "boolean", "description": "every leaf reached, not one per file"},
         }, required=["root", "query"])},
        {"name": "index.outline-map",
         "description": "One outline node's children as a map: each entry has a name and a "
                        "description to choose from and a handle with the node id to pass back "
                        "as `node` to go one level down; a leaf returns its source text. Lets the "
                        "host model do the choosing, matching `index outline-map --json`.",
         "inputSchema": root_schema({
             "node": {"type": "string", "description": "node id from a previous map; empty for the root"},
             "include_docs": {"type": "boolean"},
         })},
    ]


def call_navigate_tool(name: str, args: dict) -> dict:
    """Dispatch an MCP call to the shared payload functions."""
    root = args["root"]
    if name == "index.navigate":
        return run_navigate(root, args.get("query", ""),
                            max_files=int(args.get("max_files") or 5),
                            beam=int(args.get("beam") or DEFAULT_BEAM),
                            ratio=float(args.get("ratio") or DEFAULT_RATIO),
                            include_docs=bool(args.get("include_docs")),
                            all_leaves=bool(args.get("all_leaves")))
    if name == "index.outline-map":
        return outline_map(root, args.get("node") or "",
                           include_docs=bool(args.get("include_docs")))
    raise ValueError(f"unknown navigation tool: {name}")
