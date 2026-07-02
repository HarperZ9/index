"""Grounding handlers: verify, freshness, bench, mcp."""

from __future__ import annotations

import json

from .. import __version__
from ..context.pack import to_json
from ..graph.build import build_graph
from ._common import repo_paths, require_dir


def cmd_verify(args) -> int:
    from ..verify import build_verification

    root = require_dir(args.root)
    if (args.depends is None) == (args.exists is None):
        raise SystemExit(
            "verify: pass exactly one of --depends 'A -> B' or --exists NAME"
        )
    if args.exists is not None and not args.exists.strip():
        raise SystemExit("verify: --exists NAME must be non-empty")
    if args.depends:
        if "->" not in args.depends:
            raise SystemExit("verify: --depends must be 'A -> B'")
        frm, to = (s.strip() for s in args.depends.split("->", 1))
        claim = {"kind": "depends", "from": frm, "to": to}
        recheck = f'index verify --root "{args.root}" --depends "{args.depends}"'
    else:
        claim = {"kind": "exists", "name": args.exists.strip()}
        recheck = f'index verify --root "{args.root}" --exists "{args.exists}"'
    pack = to_json(build_graph(repo_paths(root)))
    rec = build_verification(pack, claim, tool_version=__version__, recheck=recheck)
    if args.json:
        print(json.dumps(rec, indent=2, sort_keys=True))
    else:
        loc = f" ({rec['evidence']})" if rec["evidence"] else ""
        print(f"verdict={rec['verdict']}: {rec['detail']}{loc}")
    return {"MATCH": 0, "REFUTED": 1, "UNVERIFIABLE": 2}[rec["verdict"]]


def cmd_freshness(args) -> int:
    from ..freshness import REPORT_SCHEMA, compare_freshness, workspace_fingerprint

    root = require_dir(args.root)
    try:
        cert = json.loads(args.cert.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"freshness: cannot read certificate {args.cert}: {exc}")
    stamp = cert.get("freshness") if isinstance(cert, dict) else None
    if not stamp:
        report = {
            "schema": REPORT_SCHEMA,
            "verdict": "UNVERIFIABLE",
            "detail": "certificate carries no freshness stamp "
            "(mint it with index check --freshness)",
        }
    else:
        try:
            report = compare_freshness(stamp, workspace_fingerprint(repo_paths(root)))
        except ValueError as exc:
            report = {
                "schema": REPORT_SCHEMA,
                "verdict": "UNVERIFIABLE",
                "detail": str(exc),
            }
    report["recheck"] = f'index freshness --cert "{args.cert}" --root "{args.root}"'
    return _freshness_emit(args, report)


def _freshness_emit(args, report) -> int:
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        line = f"verdict={report['verdict']}"
        if report.get("detail"):
            line += f": {report['detail']}"
        print(line)
        for n in report.get("repos_changed", []):
            print(f"  changed: {n}")
        for n in report.get("repos_added", []):
            print(f"  added: {n}")
        for n in report.get("repos_removed", []):
            print(f"  removed: {n}")
    return {"FRESH": 0, "STALE": 1, "UNVERIFIABLE": 2}[report["verdict"]]


def cmd_bench(args) -> int:
    from ..bench import bench_workspace

    root = require_dir(args.root)
    report = bench_workspace(repo_paths(root))
    report["recheck"] = f"index bench --root {args.root}"
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        st, pk = report["source_bytes"], report["pack_bytes"]
        red = report["reduction"]
        red_txt = f"  {red}x smaller" if red else ""
        print("token economy: index's structural pack vs the source it reads")
        print(
            f"  source read   {st:>11,} bytes  (~{report['approx_tokens_source']:,} "
            f"tokens)  {report['source_files']} files in {report['repos']} repos"
        )
        print(
            f"  index pack    {pk:>11,} bytes  "
            f"(~{report['approx_tokens_pack']:,} tokens){red_txt}"
        )
        print(
            f"  note: ~{report['bytes_per_token']} bytes/token is an approximation; "
            "the reduction ratio does not depend on it."
        )
        print(
            "        the pack answers structural questions (depends-on, roles, "
            "cycles); reading the code is still needed for behavior."
        )
    return 0


def cmd_mcp(args) -> int:
    from ..mcp import serve

    return serve()
