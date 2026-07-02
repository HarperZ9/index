"""Handler for `index serve`: run the on-demand verified-wiki HTTP server.

Delegates to the wiki serve module so the CLI handler stays a thin adapter and
the server logic lives with the rest of the wiki surface. Binds loopback by
default; a --host/--port override is allowed but defaults keep it local.
"""

from __future__ import annotations


def cmd_serve(args) -> int:
    from ..wiki.serve import serve_forever

    return serve_forever(host=args.host, port=args.port)
