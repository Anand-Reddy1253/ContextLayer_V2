# Convenience targets. All are thin wrappers — see docs/CONVENTIONS.md for
# what each underlying command actually does and why.

.PHONY: install dev-up dev-down test test-unit test-integration test-acceptance \
        lint typecheck fmt migrate sync-ado sync-github ui-install ui-dev

install:
	pip install -e ".[dev]"

dev-up:
	docker compose up -d postgres

dev-down:
	docker compose down

migrate:
	alembic upgrade head

test:
	pytest

test-unit:
	pytest tests/unit

test-integration:
	pytest tests/integration

test-acceptance:
	pytest tests/acceptance

lint:
	ruff check .

fmt:
	ruff format .

typecheck:
	mypy src/

sync-ado:
	context-fabric sync --source ado --fixture

sync-github:
	context-fabric sync --source github --fixture

ui-install:
	cd ui && npm install

ui-dev:
	cd ui && npm run dev
