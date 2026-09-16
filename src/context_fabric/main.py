"""FastAPI application entrypoint.

    uvicorn context_fabric.main:app --reload

Fast-tracked minimal slice (connectors + catalog routes) ahead of the
full Phase 15 consolidation, at the user's request, to validate the
connector-config UI and a real Azure DevOps live connection.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from context_fabric.api.routes import (
    catalog,
    connectors,
    context_spaces,
    org,
    retrieval,
    workflow_templates,
)
from context_fabric.settings import Settings
from context_fabric.synchronization import scheduler

settings = Settings()
logger = structlog.get_logger()


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    task: asyncio.Task[None] | None = None
    if settings.CF_SYNC_INTERVAL_SECONDS > 0:
        task = asyncio.create_task(scheduler.run_forever(settings.CF_SYNC_INTERVAL_SECONDS))
    else:
        logger.info("scheduler.disabled", reason="CF_SYNC_INTERVAL_SECONDS=0")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Context Fabric API", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CF_CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(connectors.router)
app.include_router(catalog.router)
app.include_router(org.router)
app.include_router(context_spaces.router)
app.include_router(retrieval.router)
app.include_router(workflow_templates.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
