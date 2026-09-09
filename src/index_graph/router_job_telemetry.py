"""Private router-job telemetry helpers."""
from __future__ import annotations

from time import perf_counter
from typing import Any, Callable


class RouterJobTelemetry:
    def __init__(self, started: float, append_event: Callable[[dict[str, Any]], None]) -> None:
        self._started = started
        self._append_event = append_event
        self.phase_timings_ms: dict[str, int] = {}
        self.graph_cache: dict[str, object] | None = None
        self.router_docs: dict[str, object] | None = None
        self._events: list[dict[str, Any]] = []

    def status_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if self.phase_timings_ms:
            fields["phase_timings_ms"] = dict(self.phase_timings_ms)
        if self.graph_cache is not None:
            fields["graph_cache"] = dict(self.graph_cache)
        if self.router_docs is not None:
            fields["router_docs"] = dict(self.router_docs)
        return fields

    def record_timing(self, step: str, step_started: float, **counts: Any) -> None:
        self.record_duration(step, int((perf_counter() - step_started) * 1000), **counts)

    def record_duration(self, step: str, duration_ms: int, **counts: Any) -> None:
        self.phase_timings_ms[step] = duration_ms
        event: dict[str, Any] = {
            "phase": "timing",
            "step": step,
            "duration_ms": duration_ms,
            "elapsed_ms": int((perf_counter() - self._started) * 1000),
        }
        for key, value in counts.items():
            if key in {"content", "repo_path"}:
                continue
            if isinstance(value, (bool, int, float, str)) or value is None:
                event[key] = value
        self._events.append(event)

    def flush(self) -> None:
        while self._events:
            self._append_event(self._events.pop(0))
