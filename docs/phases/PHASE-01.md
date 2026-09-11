# Phase 1 — Domain and configuration models

## Goal
Turn `docs/DOMAIN_MODEL.md` into real Pydantic v2 models in
`src/context_fabric/domain/`, and loaders for the two YAML configs
(`configs/capabilities.yaml`, `configs/stage-contracts.yaml`) that
everything downstream depends on.

## First action
Before writing any model: run `pip install -e ".[dev]"` on this machine
(Python 3.14) and confirm dependency resolution succeeds. If any pin in
`pyproject.toml` fails to resolve on 3.14, do not downgrade the host —
record it in `docs/PROGRESS.md` and rely on the Docker image's Python 3.12
pin (`Dockerfile`) for anything that needs the fallback; note which pins
were adjusted, if any, and why.

## Inputs
- `docs/DOMAIN_MODEL.md` — field-level spec for every type.
- `configs/capabilities.yaml`, `configs/stage-contracts.yaml` — shapes the
  loaders must parse.

## Files to create
- `domain/enums.py` — every enum in `docs/DOMAIN_MODEL.md` "Enums".
- `domain/errors.py` — `AuthError`, `RateLimited`, `NotFound`, `Transient`,
  `Permanent`, `SchemaDrift` (docs/CONVENTIONS.md "Error categories").
- `domain/node.py`, `domain/edge.py`, `domain/evidence.py` — with the
  layer-specific validation called out in `docs/DOMAIN_MODEL.md` (e.g. a
  TECHNICAL node requires `source_system`/`native_id`; BUSINESS/LOGICAL
  must not set them).
- `domain/context_space.py` — `ContextSpace`, `Binding`.
- `domain/sync.py` — `SyncState`, `SyncRun`.
- `domain/checkpoint.py` — `TaskCheckpoint`.
- `domain/context_pack.py` — `ContextPack` and its slot types.
- `domain/connector_types.py` — `SourceContainer`, `SourceObject`,
  `SourceContent`, `SourceLink`, `ACLReference`, `Page[T]`, `ChangePage`.
- `domain/config.py` — Pydantic models for `capabilities.yaml` and
  `stage-contracts.yaml`, plus loader functions that validate the actual
  files in `configs/` at import/startup time (fail fast on a malformed
  config, don't defer the error to first use).
- `settings.py` — `Settings(BaseSettings)` reading every variable in
  `.env.example`, with no default carrying a real secret.

## Acceptance criteria
- Every entity field-for-field matches `docs/DOMAIN_MODEL.md`. Any
  necessary deviation is called out in this phase's report, not silently
  made.
- `domain/config.py` loaders successfully parse
  `configs/stage-contracts.yaml` and `configs/capabilities.yaml` as they
  exist in the repo right now — if a loader can't parse the example
  configs, the loader is wrong.
- `domain/` has zero imports from any other `context_fabric` subpackage
  (`src/context_fabric/__init__.py` boundary rule).
- `python -c "import context_fabric.domain"` succeeds.

## Tests to write
`tests/unit/domain/` — one file per module above. Cover: valid construction
of each type, the layer-specific validation rejections (e.g. constructing
a TECHNICAL node without `source_system` raises), and successful loading
of both real config files.

## Exit gate
`pytest tests/unit -q` green. `ruff check src/context_fabric/domain` and
`mypy src/context_fabric/domain` clean. Report the Python-version finding
from "First action" explicitly, even if it was a non-event.
