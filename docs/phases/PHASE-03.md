# Phase 3 — Connector abstraction and fixture harness

## Goal
Implement the `SourceConnector` Protocol and the shared cross-cutting
infrastructure every connector will reuse, plus the anti-leakage
acceptance test that guards it forever.

## Inputs
- `docs/CONNECTORS.md` — full protocol + requirements.
- `AGENTS.md` §5/§6.

## Files to create
- `connectors/base.py` — the `SourceConnector` Protocol; `FixtureConnectorBase`
  (loads/validates JSON under `fixtures/<source>/`); `LiveConnectorBase`
  (httpx client pre-wired with timeout + tenacity retry/backoff-with-jitter
  + rate-limit-aware wait); a `@correlate` decorator/context manager that
  injects `correlation_id` into structlog bound context for every call.
- `connectors/registry.py` — maps `source_system` string -> connector
  class, one registration point `synchronization/` and `cli/` both use.

## Acceptance criteria
- The Protocol's seven methods match `docs/CONNECTORS.md` exactly in
  signature and return type.
- `FixtureConnectorBase` raises `NotFound` (not a generic exception) for a
  missing native_id, and `SchemaDrift` if a fixture file doesn't parse
  into the expected `domain/` shape.
- `LiveConnectorBase`'s retry wrapper only retries `Transient`/
  `RateLimited`; a unit test with a mocked always-`Permanent`-raising call
  proves it does *not* retry those.
- No test yet exercises a real connector (there are none until Phase 4) —
  this phase's tests exercise the base classes with a throwaway fake
  connector fixture.

## Tests to write
`tests/unit/connectors/test_base.py` — retry/backoff behavior per error
category (mock the underlying call), correlation ID propagation into log
records (capture via structlog's testing capture), fixture-mode
NotFound/SchemaDrift behavior against a small throwaway fixture directory
under `tests/unit/connectors/fixtures/`.

`tests/acceptance/test_connectors_never_leak_vendor_shapes.py` — written
now even though it has nothing to check yet beyond the base classes;
extended in Phases 4-5 to cover real connectors. Establish the pattern:
walk every registered connector's public methods via reflection, assert
every return value is a `domain/` type.

## Exit gate
`pytest tests/unit/connectors tests/acceptance/test_connectors_never_leak_vendor_shapes.py -q`
green. Confirm in the report that the anti-leakage test is written in a
way that will actually catch a Phase 4/5 regression (e.g. temporarily
break it against a throwaway fake connector to prove it fails correctly,
then revert).
