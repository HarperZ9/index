"""Pure classification: ordered glob rules, then a remote-host fallback."""

from __future__ import annotations

from urllib.parse import urlsplit

from .config import PUBLIC_HOSTS, Config


def _remote_host(origin: str) -> str | None:
    if not origin:
        return None
    if "://" not in origin and "@" in origin and ":" in origin:
        # scp-like SSH form: git@github.com:owner/repo.git
        return origin.split("@", 1)[1].split(":", 1)[0] or None
    return urlsplit(origin).hostname


def classify(path: str, is_repo: bool, origin: str, config: Config) -> str:
    for rule in config.rules:
        if rule.regex.match(path):
            return rule.class_
    if is_repo:
        host = _remote_host(origin)
        if host is None:
            return "local"
        return "public" if host in PUBLIC_HOSTS else "private"
    name = path.rsplit("/", 1)[-1]
    return "hidden" if name.startswith(".") else "entry"
