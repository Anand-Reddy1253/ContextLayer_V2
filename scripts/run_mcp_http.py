"""Runs the Context MCP server over streamable-HTTP instead of stdio — for
a remote client (Claude's remote MCP connector) reaching it through a
port-forward/tunnel, rather than a client-spawned local subprocess.

Same tools, same data, same complete lack of authentication as stdio mode
(server_stdio.py's own docstring: "Actor identity: none yet ... do not
point this at anything multi-tenant until that's built") — only the
transport differs. Never run this exposed to anything but a short,
supervised test.

CF_DATABASE_URL controls which database this reads — set it before
running to point at a specific SQLite file or Postgres instance; defaults
to whatever .env/the environment already provides otherwise.
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    # Same reasoning as scripts/run_api.py: psycopg3's async mode rejects
    # the ProactorEventLoop asyncio.run()/anyio.run() would otherwise pick
    # by default on Windows. context_fabric.persistence.session already
    # sets this at import time, so this is defensive/explicit rather than
    # load-bearing — matches run_api.py's own precedent.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from context_fabric.mcp.server_stdio import mcp  # noqa: E402

if __name__ == "__main__":
    print("Context MCP (streamable-HTTP) on http://0.0.0.0:8100/mcp", flush=True)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8100)
