"""CLI face for `index wiki`: generate the sealed artifact, or verify one.

A `source` positional accepts a git URL or a local path: a URL is shallow-cloned
to a temp dir, run, and cleaned up, so `index wiki https://github.com/org/repo`
gives the paste-a-repo experience without a server. A local path (or --root)
reads in place. The clone is a normal git clone: nothing is fetched that a plain
`git clone --depth 1` would not fetch, and the temp dir is always removed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

_URL_SCHEMES = ("http://", "https://", "git://", "ssh://", "file://")


def add_wiki_parser(sub) -> None:
    w = sub.add_parser(
        "wiki",
        help="Single-repo verified wiki: pages derived from the module graph, "
             "sealed and commit-pinned; --verify re-checks a sealed artifact.")
    w.add_argument("source", nargs="?", default=None,
                   help="a git URL (shallow-cloned then removed) or a local path "
                        "to derive the wiki from; overrides --root when given")
    w.add_argument("--root", type=Path, default=Path.cwd(),
                   help="the single repo to derive the wiki from")
    w.add_argument("--out", default=None, help="write the artifact to this path")
    w.add_argument("--format", choices=["html", "json"], default="html")
    w.add_argument("--verify", type=Path, default=None,
                   help="verify a sealed wiki artifact against the current tree "
                        "(MATCH/DRIFT/UNVERIFIABLE, exit 0/1/2)")
    w.add_argument("--json", action="store_true",
                   help="with --verify, emit the verification report as JSON")


def _emit_report(report: dict, as_json: bool) -> int:
    from .seal import VERDICT_EXIT
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"verdict={report['verdict']} pages={report['pages_checked']} "
              f"edges={report['edges_checked']}")
        for finding in report["findings"]:
            print(f"  [{finding['rule']}] {finding['detail']}")
    return VERDICT_EXIT[report["verdict"]]


def _is_url(source: str) -> bool:
    return source.startswith(_URL_SCHEMES) or source.startswith("git@")


def _clone(source: str) -> Path:
    dest = Path(tempfile.mkdtemp(prefix="index-wiki-"))
    try:
        subprocess.run(["git", "clone", "--depth", "1", source, str(dest)],
                       check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise SystemExit(f"could not clone {source}: {exc}") from exc
    return dest


def _resolve_source(source: str) -> tuple[Path, Path | None]:
    """Return (root, tempdir-to-clean). A URL is cloned; a local path is read in
    place; anything else is rejected rather than silently treated as a path."""
    if _is_url(source):
        clone = _clone(source)
        return clone, clone
    path = Path(source)
    if path.is_dir():
        return path.resolve(), None
    raise SystemExit(f"source is not a git URL or an existing directory: {source}")


def cmd_wiki(args) -> int:
    if args.verify is not None:
        from .seal import run_verify
        return _emit_report(run_verify(args.verify, args.root.resolve()), args.json)
    root, tmp = (_resolve_source(args.source) if args.source
                 else (args.root.resolve(), None))
    try:
        if not root.is_dir():
            raise SystemExit(f"root not found: {root}")
        return _generate(root, args)
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def _generate(root: Path, args) -> int:
    from .pack import build_wiki_pack
    pack = build_wiki_pack(root)
    if args.format == "json":
        text = json.dumps(pack, indent=2, sort_keys=True)
    else:
        from .html import render_wiki_html
        text = render_wiki_html(pack)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0
