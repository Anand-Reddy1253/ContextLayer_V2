# ADR-005: Fixture-first connector protocol

## Status
Accepted

## Context
Every connector needs to behave identically under test regardless of
whether the target vendor system is reachable, and every connector needs
the same cross-cutting behavior (retry, backoff, rate limiting, pagination,
error categorization) without reimplementing it per vendor.

## Decision
One `SourceConnector` Protocol (`docs/CONNECTORS.md`) with eight async
methods, implemented twice per source: a **fixture** implementation reading
deterministic JSON from `fixtures/<source>/` (default, no network, no
credentials — this is what CI and acceptance tests run against), and a
**live** implementation calling the real vendor API, gated by environment
variables and off unless explicitly enabled.

Cross-cutting concerns (timeout, bounded exponential backoff with jitter,
rate-limit awareness, correlation IDs, structured logging, error
categorization) live once in `connectors/base.py`, not per connector.
Vendor payload shapes are translated to `domain/` models inside each
connector's `mapper.py` and never cross that boundary (ADR-001,
`AGENTS.md` §5).

Azure DevOps is the first connector implemented (Phase 4) and is the
reference every later connector follows; GitHub (Phase 5) is the proof that
the abstraction generalizes.

## Consequences
- Every acceptance test in the project can run without any live
  credential, anywhere, including CI.
- Adding a connector means writing a mapper and fixtures, not
  rediscovering retry/pagination/logging behavior.
- Live mode is opt-in per deployment (Phase 19) and is explicitly the last
  phase, not a prerequisite for anything earlier.
