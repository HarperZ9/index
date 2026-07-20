"""Monotonic cooperative work budgets for bounded routing."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Callable


_COUNTERS = (
    "repositories_visited",
    "directories_visited",
    "candidate_documents_observed",
    "document_bodies_opened",
    "files_validated",
)


@dataclass
class WorkBudget:
    """Track bounded route work against a monotonic deadline."""

    requested_ms: int
    started_at: float
    deadline: float
    clock: Callable[[], float] = field(repr=False)
    counters: dict[str, int] = field(
        default_factory=lambda: {name: 0 for name in _COUNTERS}
    )
    exhausted_at: str | None = None

    @classmethod
    def start(
        cls, budget_ms: int, *, clock: Callable[[], float] = monotonic
    ) -> "WorkBudget":
        """Start a budget whose deadline is relative to one monotonic reading."""
        if budget_ms < 1:
            raise ValueError("budget_ms must be >= 1")
        started = clock()
        return cls(budget_ms, started, started + budget_ms / 1000, clock)

    def checkpoint(
        self, boundary: str, *, counter: str | None = None, amount: int = 1
    ) -> bool:
        """Reserve work at *boundary*, recording the first deadline exhaustion."""
        if amount < 0:
            raise ValueError("amount must be >= 0")
        if self.exhausted_at is not None or self.clock() >= self.deadline:
            self.exhausted_at = self.exhausted_at or boundary
            return False
        if counter is not None:
            if counter not in self.counters:
                raise ValueError(f"unknown budget counter: {counter}")
            self.counters[counter] += amount
        return True

    def callback(self, counter: str | None = None) -> Callable[[str], bool]:
        """Return a checkpoint callback suitable for cooperative walkers."""
        return lambda boundary: self.checkpoint(boundary, counter=counter)

    @property
    def exhausted(self) -> bool:
        """Whether a checkpoint has observed the deadline."""
        return self.exhausted_at is not None

    def to_json(self) -> dict[str, int | str | None]:
        """Return the portable budget portion of a route receipt."""
        elapsed_ms = max(0, round((self.clock() - self.started_at) * 1000))
        return {
            "requested_ms": self.requested_ms,
            "elapsed_ms": elapsed_ms,
            **self.counters,
            "exhausted_at": self.exhausted_at,
        }
