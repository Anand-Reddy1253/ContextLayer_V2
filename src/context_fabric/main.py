"""FastAPI application entrypoint.

    uvicorn context_fabric.main:app --reload

Fast-tracked minimal slice (connectors + catalog routes) ahead of the
full Phase 15 consolidation, at the user's request, to validate the
connector-config UI and a real Azure DevOps live connection.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from context_fabric.api.routes import catalog, connectors, context_spaces, org
from context_fabric.settings import Settings

settings = Settings()

app = FastAPI(title="Context Fabric API")

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


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
