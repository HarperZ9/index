"""Small private helpers for durable router jobs."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def root_hash(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode("utf-8", "surrogateescape")).hexdigest()[:16]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8", "surrogateescape"))


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def request_sha256(request: dict[str, Any]) -> str:
    return sha256_text(canonical_json(dict(request)))


def config_sha256(root: Path) -> str:
    parts: list[list[str]] = []
    for name in (".index.toml", ".repomap.toml"):
        path = root / name
        if not path.exists():
            parts.append([name, "missing"])
            continue
        try:
            parts.append([name, sha256_bytes(path.read_bytes())])
        except OSError:
            parts.append([name, "unreadable"])
    return sha256_text(canonical_json({"root": str(root.resolve()), "config": parts}))


def safe_error_message(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    return " ".join(text.split())[:500]
