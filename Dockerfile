# Context Fabric API + Context MCP (HTTP transport) image.
# See docs/CONVENTIONS.md for the rationale on pinned base image + slim layers.
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -e ".[dev]"

COPY configs ./configs
COPY fixtures ./fixtures
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
RUN chmod +x scripts/docker-entrypoint.sh

EXPOSE 8000 8100

ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "context_fabric.main:app", "--host", "0.0.0.0", "--port", "8000"]
