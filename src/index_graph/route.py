"""Explicit-path task routing backed by the context-envelope contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

from .context.envelope import build_context_envelope
from .graph.build import build_graph
from .scan import repo_key_map

SCHEMA = "index.route/v1"


def _root_hash(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return path.name


def _path_hash(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8", errors="surrogatepass")).hexdigest()


def _reject(path: str, reason_code: str, rule_ref: str, **extra: object) -> dict:
    return {"path": path, "reason_code": reason_code, "rule_ref": rule_ref, **extra}


def _outside_root_rejection(raw: Path, candidate: Path) -> dict:
    digest = _path_hash(candidate)
    return _reject(
        f"outside-root:{digest[:16]}",
        "outside-root",
        "route.explicit_path.contained",
        path_kind="outside-root",
        path_sha256=digest,
        was_absolute=raw.is_absolute(),
    )


def _selected(path: Path, root: Path, key: str) -> dict:
    return {"key": key, "path": _rel(path, root)}


def _normalize_candidate(root: Path, raw_path: str) -> tuple[Path | None, dict | None]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, _reject(str(raw_path), "empty-path", "route.explicit_path.nonempty")
    raw = Path(raw_path)
    candidate = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, _outside_root_rejection(raw, candidate)
    portable_path = _rel(candidate, root)
    if not candidate.exists():
        return None, _reject(portable_path, "not-found", "route.explicit_path.exists")
    if not candidate.is_dir():
        return None, _reject(portable_path, "not-directory", "route.explicit_path.directory")
    if not (candidate / ".git").exists():
        return None, _reject(portable_path, "not-repository", "route.explicit_path.repository")
    return candidate, None


def _portable_envelope(envelope: dict) -> dict:
    data = json.loads(json.dumps(envelope, sort_keys=True))
    data["root"] = "."
    data["recheck"] = {
        **data.get("recheck", {}),
        "command": "index route --root ROOT --path PATH --json",
    }
    return data


def _empty_receipt(root: Path, *, paths: Sequence[str], rejected: list[dict]) -> dict:
    return {
        "schema": SCHEMA,
        "status": "UNVERIFIABLE",
        "failure_codes": ["no_selected_repositories"],
        "root": {"sha256_prefix": _root_hash(root)},
        "mode": "explicit-path",
        "selection": {"selected": [], "rejected": rejected},
        "reconciliation": {
            "candidate_count": len(paths),
            "selected_count": 0,
            "rejected_count": len(rejected),
            "omitted_count": 0,
        },
        "envelope": None,
        "privacy": {"absolute_paths_included": False},
        "recheck": {"command": "index route --root ROOT --path PATH --json"},
    }


def build_route(
    root: Path | str,
    *,
    paths: Sequence[str],
    token_budget: int = 1200,
    hops: int | None = None,
) -> dict:
    """Build a route envelope for explicit repository paths without workspace discovery."""
    root_path = Path(root).resolve()
    raw_paths = [str(item) for item in paths]
    if token_budget < 1:
        raise ValueError("budget must be a positive integer")
    if hops is not None and hops < 0:
        raise ValueError("hops must be non-negative")
    rejected: list[dict] = []
    selected_paths: list[Path] = []
    seen: set[Path] = set()
    for raw_path in raw_paths:
        candidate, rejection = _normalize_candidate(root_path, raw_path)
        if rejection is not None:
            rejected.append(rejection)
            continue
        assert candidate is not None
        if candidate in seen:
            rejected.append(_reject(_rel(candidate, root_path), "duplicate-path", "route.explicit_path.unique"))
            continue
        seen.add(candidate)
        selected_paths.append(candidate)
    if not selected_paths:
        return _empty_receipt(root_path, paths=raw_paths, rejected=rejected)

    keyed = repo_key_map(root_path, sorted(selected_paths), include_root_repo=True)
    graph = build_graph(keyed, executor="thread")
    envelope = _portable_envelope(build_context_envelope(
        graph,
        root=root_path,
        token_budget=token_budget,
        hops=hops,
    ))
    envelope_verified = envelope.get("verification_verdict") == "MATCH"
    if not envelope_verified:
        status = "UNVERIFIABLE"
        failure_codes = ["envelope_unverifiable"]
        if rejected:
            failure_codes.append("candidate_rejected")
    elif rejected:
        status = "PARTIAL"
        failure_codes = ["candidate_rejected"]
    else:
        status = "MATCH"
        failure_codes = []
    return {
        "schema": SCHEMA,
        "status": status,
        "failure_codes": failure_codes,
        "root": {"sha256_prefix": _root_hash(root_path)},
        "mode": "explicit-path",
        "selection": {
            "selected": [
                _selected(path, root_path, key)
                for key, path in sorted(keyed.items(), key=lambda item: item[0])
            ],
            "rejected": rejected,
        },
        "reconciliation": {
            "candidate_count": len(raw_paths),
            "selected_count": len(keyed),
            "rejected_count": len(rejected),
            "omitted_count": 0,
        },
        "envelope": envelope,
        "privacy": {"absolute_paths_included": False},
        "recheck": {"command": "index route --root ROOT --path PATH --json"},
    }


def cmd_route(args) -> int:
    try:
        payload = build_route(
            args.root,
            paths=args.paths,
            token_budget=args.budget,
            hops=args.hops,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"route status={payload['status']} "
            f"selected={payload['reconciliation']['selected_count']} "
            f"rejected={payload['reconciliation']['rejected_count']}"
        )
    return 0 if payload["status"] == "MATCH" else 2


def call_route(args: dict, *, response_id=None) -> dict:
    if not isinstance(args, dict):
        raise ValueError("route arguments must be an object")
    allowed = {"root", "paths", "budget", "hops"}
    if set(args) - allowed:
        raise ValueError("unexpected route arguments")
    root = args.get("root")
    paths = args.get("paths")
    if not isinstance(root, str) or not root.strip():
        raise ValueError("root must be a non-empty string")
    if (
        not isinstance(paths, list)
        or not paths
        or any(not isinstance(item, str) for item in paths)
    ):
        raise ValueError("paths must be a non-empty list of strings")
    budget = args.get("budget", 1200)
    if type(budget) is not int or budget < 1:
        raise ValueError("budget must be a positive integer")
    hops = args.get("hops")
    if hops is not None and (type(hops) is not int or hops < 0):
        raise ValueError("hops must be a non-negative integer")
    return build_route(
        Path(root),
        paths=paths,
        token_budget=budget,
        hops=hops,
    )


def tool_definition() -> dict:
    return {
        "name": "index.route",
        "description": (
            "Build a receipt-backed context envelope for explicit repository paths "
            "without discovering unrelated workspace repositories."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "root": {"type": "string", "minLength": 1},
                "paths": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string"},
                },
                "budget": {"type": "integer", "minimum": 1, "default": 1200},
                "hops": {"type": "integer", "minimum": 0},
            },
            "required": ["root", "paths"],
        },
    }
