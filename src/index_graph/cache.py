"""Small filesystem cache for expensive workspace-wide index surfaces."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from time import time
from typing import Any, Callable

SCHEMA = "index.cache-entry/v1"


def _ttl_seconds() -> float:
    raw = os.environ.get("INDEX_CACHE_TTL_SECONDS", "900")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 900.0


def _cache_dir() -> Path:
    raw = os.environ.get("INDEX_CACHE_DIR")
    if raw:
        return Path(raw)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "index_graph" / "cache"
    return Path.home() / ".cache" / "index_graph"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def workspace_signature(root: Path) -> str:
    """Cheap workspace signature for cache invalidation.

    This is intentionally cheaper than the full freshness fingerprint. It catches
    config and top-level entry changes, while the TTL bounds nested-change staleness.
    """
    root = root.resolve()
    parts = [str(root)]
    for cfg in (root / ".index.toml", root / ".repomap.toml"):
        try:
            stat = cfg.stat()
        except OSError:
            parts.append(f"{cfg.name}:missing")
        else:
            parts.append(f"{cfg.name}:{stat.st_mtime_ns}:{stat.st_size}")
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError as exc:
        parts.append(f"root-error:{type(exc).__name__}:{exc}")
        return _sha256_text("|".join(parts))
    for entry in entries:
        try:
            stat = entry.stat()
        except OSError:
            parts.append(f"{entry.name}:unstatable")
            continue
        kind = "d" if entry.is_dir() else "f"
        parts.append(f"{entry.name}:{kind}:{stat.st_mtime_ns}:{stat.st_size}")
    return _sha256_text("|".join(parts))


def _key(tool: str, root: Path, args: dict[str, Any]) -> str:
    payload = {
        "tool": tool,
        "root": str(root.resolve()),
        "args": args,
        "workspace_signature": workspace_signature(root),
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_text(body)


def _path(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def cached_text(
    tool: str,
    root: Path,
    args: dict[str, Any],
    build: Callable[[], str],
    *,
    enabled: bool = True,
) -> str:
    ttl = _ttl_seconds()
    if not enabled or ttl <= 0:
        return build()
    key = _key(tool, root, args)
    path = _path(key)
    now = time()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") == SCHEMA and now - float(data.get("created_at", 0.0)) <= ttl:
            return str(data.get("text", ""))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    text = build()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema": SCHEMA, "created_at": now, "text": text}, separators=(",", ":")),
            encoding="utf-8",
        )
    except OSError:
        pass
    return text
