"""Run the API with the Windows event-loop policy fix actually applied.

`uvicorn.run(...)` calls `asyncio.run(...)`, which always creates a brand
new event loop via the loop factory regardless of anything set
beforehand — so setting WindowsSelectorEventLoopPolicy and then calling
`uvicorn.run()` (even with loop="asyncio") still ends up on a
ProactorEventLoop, which psycopg3's async mode rejects. Instead, this
creates the loop ourselves (respecting the policy) and drives
uvicorn.Server.serve() directly on it, bypassing uvicorn's own
asyncio.run() call entirely.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402


async def _main() -> None:
    config = uvicorn.Config("context_fabric.main:app", host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print(f"event loop: {type(loop).__name__}", flush=True)
    loop.run_until_complete(_main())
