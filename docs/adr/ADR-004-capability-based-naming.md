# ADR-004: Capability-based, vendor-neutral naming

## Status
Accepted

## Context
The original per-team boundary was described in vendor terms — "repo
location," "Confluence location," "Jira location." That works for one team
and breaks the moment two teams serve the same SDLC need with different
vendors (one team's work tracker is ADO, another's is Jira). Naming by
vendor also leaks vendor identity into retrieval and stage-contract logic
that should not care which product is behind a capability.

## Decision
Introduce an SDLC capability vocabulary (`configs/capabilities.yaml`):
`CODE`, `DOCUMENTATION`, `WORK_MANAGEMENT`, `CHANGE_REVIEW`,
`BUILD_RELEASE`, `QUALITY`, `POLICY`. Every binding in a `ContextSpace`
(`docs/DOMAIN_MODEL.md`) names a capability and a connector instance that
serves it for that team — never a bare vendor name. Stage contracts
(`configs/stage-contracts.yaml`) request slots by capability, not by
source system.

## Consequences
- Two teams can serve `WORK_MANAGEMENT` from ADO and Jira respectively with
  zero retrieval code difference.
- Adding a new vendor for an existing capability (e.g. Notion for
  `DOCUMENTATION`) is a new connector plus new bindings — stage contracts
  and the pack compiler need no change.
- The vocabulary is intentionally small and fixed for v1. Adding a
  capability is a config change reviewed like a schema change, not
  something invented per-team.
