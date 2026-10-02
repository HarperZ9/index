"""Rate-limited graph diagnostics, separate from CLI/MCP result streams."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict

from .build import GraphProgress


def stderr_progress():
    last_phase = None
    last_ms = -1000

    def report(event: GraphProgress) -> None:
        nonlocal last_phase, last_ms
        if event.phase == last_phase and event.elapsed_ms - last_ms < 1000:
            return
        last_phase, last_ms = event.phase, event.elapsed_ms
        try:
            print(json.dumps({"schema": "index.graph-progress/v1", **asdict(event)}),
                  file=sys.stderr, flush=True)
        except OSError:
            # Losing a diagnostic sink must not change dependency evidence.
            pass

    return report
