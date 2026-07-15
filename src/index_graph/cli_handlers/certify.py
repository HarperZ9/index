"""Certificate handlers: check, snapshot, drift."""

from __future__ import annotations

import json

from .. import __version__
from ..config import load_config
from ..context.pack import to_json
from ..graph.build import build_graph
from ._common import emit_cert, repo_paths, require_dir


def cmd_check(args) -> int:
    from ..arch.check import check_graph
    from ..certify import build_certificate
    from ..freshness import workspace_fingerprint

    root = require_dir(args.root)
    config = load_config(args.config, root)
    crit = config.architecture
    paths = repo_paths(root)
    graph = build_graph(paths)
    pack = to_json(graph)
    names = set(pack.get("roles", {}).keys())
    fresh_stamp = workspace_fingerprint(paths) if args.freshness else None
    fresh_flag = " --freshness" if args.freshness else ""

    if not crit.declared:
        cert = build_certificate(
            "check",
            content=pack,
            criterion=None,
            verdict="UNVERIFIABLE",
            findings=[
                {
                    "rule": "criterion",
                    "detail": "no [architecture] criterion declared",
                    "edge": None,
                    "evidence": None,
                }
            ],
            recheck=f"index check --root {args.root}{fresh_flag}",
            tool_version=__version__,
            freshness=fresh_stamp,
        )
        return emit_cert(cert, args.json)

    findings = [
        {"rule": f.rule, "detail": f.detail, "edge": f.edge, "evidence": f.evidence}
        for f in check_graph(pack, crit)
    ]
    internal_content = _check_internals(args, crit, paths, findings)
    # an internal graph the analyzer could not fully build (parse errors /
    # unreadable files) must not yield a MATCH: the map would certify structure
    # it could not fully see.
    internal_incomplete = internal_content is not None and any(
        not repo.get("coverage", {}).get("complete", True)
        for repo in internal_content.values())
    # a *_unmatched rule (require_unmatched, forbid_unmatched) is a
    # criterion-quality gap (UNVERIFIABLE), not a breach; capture
    # real_violations BEFORE layer findings are appended (order matters).
    real_violations = any(not f["rule"].endswith("_unmatched") for f in findings)
    unmatched = _check_layers(crit, names, findings)
    verdict = _check_verdict(real_violations, unmatched, findings, internal_incomplete)
    cert = _check_certificate(
        args, crit, pack, internal_content, findings, verdict, fresh_stamp, fresh_flag
    )
    return emit_cert(cert, args.json)


def _check_internals(args, crit, paths, findings) -> dict | None:
    # optional intra-repo module checks: internal cycles against the ceiling
    if not args.internals:
        return None
    from ..internals import build_internals

    internal_content: dict = {}
    for name, p in sorted(paths.items()):
        g = build_internals(p, name)
        internal_content[name] = {
            "cycles": [list(c) for c in g.cycles],
            "coverage": {
                "complete": g.coverage.complete,
                "parse_errors": list(g.coverage.parse_errors),
                "dynamic_imports": [
                    {"file": fpath, "line": ln}
                    for fpath, ln in g.coverage.dynamic_imports
                ],
            },
        }
        if crit.max_cycles is not None and len(g.cycles) > crit.max_cycles:
            findings.append(
                {
                    "rule": "max_cycles",
                    "detail": f"{name}: {len(g.cycles)} internal module cycle(s) "
                    f"exceed the ceiling of {crit.max_cycles}",
                    "edge": None,
                    "evidence": None,
                }
            )
    return internal_content


def _check_layers(crit, names, findings) -> list[str]:
    # criterion-quality warnings: layers that name no repo
    unmatched = [
        layer
        for layer in crit.layers
        if not any(
            n == layer or n.startswith(layer + "/") or n.endswith("/" + layer)
            for n in names
        )
    ]
    for layer in unmatched:
        findings.append(
            {
                "rule": "layer",
                "detail": f"layer '{layer}' matches no repo",
                "edge": None,
                "evidence": None,
            }
        )
    return unmatched


def _check_verdict(real_violations, unmatched, findings, internal_incomplete=False) -> str:
    # a confirmed breach outranks an unverifiable criterion
    if real_violations:
        return "DRIFT"
    # a *_unmatched criterion gap, an unmatched layer, or an internal graph the
    # analyzer could not fully build (parse errors) all read UNVERIFIABLE: a
    # MATCH must not be issued over a graph that is not fully derivable
    if (unmatched or internal_incomplete
            or any(f["rule"].endswith("_unmatched") for f in findings)):
        return "UNVERIFIABLE"
    return "MATCH"


def _check_certificate(
    args, crit, pack, internal_content, findings, verdict, fresh_stamp, fresh_flag
):
    from ..certify import build_certificate

    criterion_doc = {
        "layers": list(crit.layers),
        "forbid": [{"from": f.from_glob, "to": f.to_glob} for f in crit.forbid],
        "max_cycles": crit.max_cycles,
        "owns": [list(o) for o in crit.owns],
    }
    if crit.require:  # keep empty-require criteria byte-identical (hash stability)
        criterion_doc["require"] = [
            {"from": r.from_glob, "to": r.to_glob} for r in crit.require
        ]
    content = (
        pack
        if internal_content is None
        else {"pack": pack, "internals": internal_content}
    )
    coverage_doc = None
    if internal_content is not None:
        incomplete = {
            n: internal_content[n]["coverage"]
            for n in internal_content
            if not internal_content[n]["coverage"]["complete"]
        }
        coverage_doc = {"complete": not incomplete, "unverifiable_repos": incomplete}
    recheck = (
        f"index check --root {args.root}"
        + (" --internals" if args.internals else "")
        + fresh_flag
    )
    return build_certificate(
        "check",
        content=content,
        criterion=criterion_doc,
        verdict=verdict,
        findings=findings,
        recheck=recheck,
        tool_version=__version__,
        coverage=coverage_doc,
        freshness=fresh_stamp,
    )


def cmd_snapshot(args) -> int:
    from ..drift import dumps_canonical, snapshot_pack

    root = require_dir(args.root)
    graph = build_graph(repo_paths(root))
    snap = snapshot_pack(to_json(graph))
    args.out.write_text(dumps_canonical(snap), encoding="utf-8")
    print(f"wrote {args.out} repos={len(snap['repos'])} edges={len(snap['edges'])}")
    return 0


def cmd_drift(args) -> int:
    from ..drift import diff_snapshots, load_snapshot

    old = load_snapshot(args.from_snap.read_text(encoding="utf-8"))
    new = load_snapshot(args.to_snap.read_text(encoding="utf-8"))
    try:
        report = diff_snapshots(old, new)
    except ValueError as exc:
        raise SystemExit(f"drift: {exc}")
    if args.json:
        print(json.dumps(report.to_json(), indent=2))
    else:
        print(f"verdict={report.verdict}")
        for e in report.edges_added:
            print(f"  edge added: {e}")
        for e in report.edges_removed:
            print(f"  edge removed: {e}")
    return 0 if report.verdict == "MATCH" else 1
