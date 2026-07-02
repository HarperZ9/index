"""CLI face for `index wiki`: generate the sealed artifact, or verify one."""
from __future__ import annotations

import json
from pathlib import Path


def add_wiki_parser(sub) -> None:
    w = sub.add_parser(
        "wiki",
        help="Single-repo verified wiki: pages derived from the module graph, "
             "sealed and commit-pinned; --verify re-checks a sealed artifact.")
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


def cmd_wiki(args) -> int:
    root = args.root.resolve()
    if args.verify is not None:
        from .seal import run_verify
        return _emit_report(run_verify(args.verify, root), args.json)
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
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
