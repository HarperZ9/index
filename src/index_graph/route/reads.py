"""Root-contained, shared document-body reads for bounded routes."""
from __future__ import annotations

from pathlib import Path

from .budget import WorkBudget


class DocumentReader:
    """Cache portable document bodies while enforcing one route-wide body cap."""

    def __init__(self, root: Path | str, max_docs: int, budget: WorkBudget) -> None:
        if max_docs < 0:
            raise ValueError("max_docs must be >= 0")
        self.root = Path(root).resolve()
        self.max_docs = max_docs
        self.budget = budget
        self._bodies: dict[str, str] = {}
        self._reasons: dict[str, str] = {}

    def _path_key(self, path: Path | str) -> tuple[Path, str | None, str]:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(self.root).as_posix()
        except ValueError:
            return resolved, None, resolved.as_posix()
        return resolved, relative, relative

    def read(self, path: Path | str) -> str | None:
        """Return a cached or newly opened UTF-8 body, or a typed failure."""
        resolved, relative, reason_key = self._path_key(path)
        if relative is None:
            self._reasons[reason_key] = "outside-root"
            return None
        if relative in self._bodies:
            return self._bodies[relative]
        if relative in self._reasons:
            return None
        if len(self._bodies) >= self.max_docs:
            self._reasons[relative] = "max-docs"
            return None
        if not self.budget.checkpoint(
            "docs.open", counter="document_bodies_opened"
        ):
            self._reasons[relative] = "budget-exhausted"
            return None
        try:
            body = resolved.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            self._reasons[relative] = "not-found"
            return None
        except OSError:
            self._reasons[relative] = "unreadable"
            return None
        self._bodies[relative] = body
        return body

    def reason(self, path: Path | str) -> str | None:
        """Return the stable failure reason recorded for *path*, if any."""
        _, relative, reason_key = self._path_key(path)
        return self._reasons.get(relative if relative is not None else reason_key)

    def bodies(self) -> dict[str, str]:
        """Return a defensive copy of root-relative cached bodies."""
        return self._bodies.copy()
