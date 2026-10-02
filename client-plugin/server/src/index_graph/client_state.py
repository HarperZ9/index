"""Explicit client-owned persistence using the existing cache/map/job engines."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from .client_mcp import MAX_ENTRIES, ClientRefusal, confined


def validate_state(state: Path) -> Path:
    state = confined(state, str(state), tree=True)
    if not state.is_dir():
        raise ClientRefusal("state directory must exist")
    # Persistence is private. A hard-linked output could mutate a file elsewhere.
    count = 0
    for folder, dirs, files in os.walk(state, followlinks=False):
        for name in [*dirs, *files]:
            count += 1
            if count > MAX_ENTRIES:
                raise ClientRefusal("state directory exceeds local client entry limit")
            path = confined(state, str(Path(folder) / name))
            if path.is_file() and path.stat().st_nlink != 1:
                raise ClientRefusal("state files cannot have hard links")
    return state


def invoke_state(name, args, root, state):
    if name == "index.map":
        from . import __version__
        from .cache import cached_text
        from .config import default_config
        from .scan import build_map
        for key in ("no_cache",):
            if key in args and type(args[key]) is not bool:
                raise ClientRefusal(f"{key} must be boolean", "ARGUMENTS_DENIED")
        path = confined(root, args["root"], tree=True)
        return cached_text("index.map", path, {"version": __version__},
            lambda: json.dumps(build_map(path, default_config(), __version__).to_json()),
            enabled=not args.get("no_cache", False), cache_root=state / "cache")
    from . import router_jobs
    action = name.rsplit(".", 1)[-1]
    operations = {"status": router_jobs.read_router_job_status,
                  "result": router_jobs.read_router_job_result,
                  "cancel": router_jobs.cancel_router_job}
    if action not in operations:
        raise ClientRefusal("starting or resuming workers requires a separate process grant", "TOOL_NOT_GRANTED")
    job_id = str(uuid.UUID(args["job_id"]))
    job = confined(state, str(state / "jobs" / job_id), tree=True)
    request_path = confined(state, str(job / "request.json"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("schema") != "index.router-job-request/v1" or request.get("job_id") != job_id:
        raise ClientRefusal("invalid owned job request")
    confined(root, request.get("root"), tree=True)
    return json.dumps(operations[action](job_id, job_root=state / "jobs"))
