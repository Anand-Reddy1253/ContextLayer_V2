# Phase 19 — Optional live connector activation

## Goal
The only phase gated on an external precondition: real credentials for
Azure DevOps and/or GitHub. **Do not attempt this phase without
credentials actually available** — it is optional and explicitly last for
that reason.

## Inputs
- `connectors/azure_devops/live.py`, `connectors/github/live.py` — the
  `NotImplementedError` stubs from Phases 4-5.
- `.env.example`'s live-mode variable names (`CF_ADO_ORG_URL`,
  `CF_ADO_PAT`, `CF_GITHUB_APP_ID`/`CF_GITHUB_TOKEN`).
- `connectors/base.py`'s `LiveConnectorBase` (Phase 3) — the
  timeout/retry/backoff/rate-limit stack already exists; this phase wires
  real HTTP calls into it, it does not rebuild that infrastructure.

## Files to change
- `connectors/azure_devops/live.py`, `connectors/github/live.py` — replace
  the `NotImplementedError` stub bodies with real `httpx` calls against
  each vendor's REST API, using `LiveConnectorBase`, mapped through the
  *same* `mapper.py` files fixture mode uses (a live payload and a fixture
  payload should map to identical `domain/` shapes for the same logical
  object — this is the actual test of whether the fixtures were
  representative).

## Acceptance criteria
- `context-fabric sync --source ado --live` against a real (test/sandbox)
  ADO org produces nodes structurally consistent with what fixture mode
  produces for equivalent data (same fields populated, same hierarchy
  shape).
- Rate-limit and auth-error handling is exercised against the real API at
  least once each (e.g. deliberately use an expired PAT to confirm
  `AuthError` is raised correctly, not swallowed).
- No credential appears in any log line or is committed anywhere
  (`docs/SECURITY.md`) — re-verify this specifically against real
  credential values, not just the fixture-mode redaction test from Phase
  14.
- The idempotency gate (Phase 6) still holds in live mode: running the
  same live sync twice with no upstream changes produces zero net graph
  change.

## Tests to write
Live-mode tests are **not** part of the default `pytest` run (they require
real credentials) — gate them behind an explicit marker
(`@pytest.mark.live`) and a `CF_MODE=live` environment check, excluded from
`make test` by default, run only via a separate documented command
(`pytest -m live`) when credentials are present.

## Exit gate
If credentials are available: `pytest -m live -q` green, plus the manual
verification steps above documented in the report. If credentials are
**not** available: report explicitly that this phase was not attempted and
why — do not simulate or fake live-mode success. The project is complete
and usable without this phase; it does not block anything else.
