"""A small repository for navigation tests, with one obvious home per topic."""
from __future__ import annotations

from pathlib import Path

FILES = {
    "src/net/retry.py": '''"""Retry logic with exponential backoff for network calls."""
import time

MAX_ATTEMPTS = 5


def backoff_delay(attempt):
    """Exponential backoff delay in seconds for a retry attempt."""
    return min(2 ** attempt, 30)


def retry_call(func, attempts=MAX_ATTEMPTS):
    """Call func, retrying with backoff when it raises a connection error."""
    for attempt in range(attempts):
        try:
            return func()
        except ConnectionError:
            time.sleep(backoff_delay(attempt))
    raise ConnectionError("retries exhausted")
''',
    "src/net/http.py": '''"""HTTP client helpers."""


class HttpClient:
    """Send requests and parse responses."""

    def get(self, url):
        """Fetch a url and return the response body."""
        return url

    def parse_headers(self, raw):
        """Split raw header lines into a dictionary."""
        return dict(line.split(": ", 1) for line in raw.splitlines())
''',
    "src/store/cache.py": '''"""A small in-memory cache with expiry."""


def cache_get(store, key):
    """Return a cached value or None when the entry expired."""
    return store.get(key)


def cache_put(store, key, value):
    """Store a value under key."""
    store[key] = value
''',
    "src/store/empty.py": "",
    "src/report/render.py": '''"""Render a report as markdown tables."""


def render_table(rows):
    """Format rows as a markdown table."""
    return "\\n".join("| " + " | ".join(r) + " |" for r in rows)
''',
    "README.md": "# demo\n\nRetry backoff is explained here at length.\n",
}


def make_repo(root: Path) -> Path:
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root
