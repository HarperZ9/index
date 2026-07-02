"""The verified wiki: single-repo pages derived from the real module graph,
joined with authored docs, sealed with per-page hashes, pinned to a commit,
and re-checkable with `index wiki --verify` (MATCH/DRIFT/UNVERIFIABLE)."""
from __future__ import annotations

from .pack import CLUSTER_THRESHOLD, build_wiki_pack
from .html import render_wiki_html
from .seal import (WIKI_SCHEMA, extract_embedded_pack, load_artifact,
                   run_verify, verify_wiki)
from .cli import CloneError, add_wiki_parser, clone_repo, cmd_wiki
from . import serve
from .serve import make_server, parse_route, serve_forever

__all__ = [
    "WIKI_SCHEMA", "CLUSTER_THRESHOLD", "build_wiki_pack", "render_wiki_html",
    "verify_wiki", "run_verify", "load_artifact", "extract_embedded_pack",
    "add_wiki_parser", "cmd_wiki", "CloneError", "clone_repo",
    "serve", "make_server", "parse_route", "serve_forever",
]
