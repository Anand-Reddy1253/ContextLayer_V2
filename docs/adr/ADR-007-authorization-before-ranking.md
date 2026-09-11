# ADR-007: Authorization filtering before ranking

## Status
Accepted

## Context
Two orderings are possible: rank/compile first and filter unauthorized
results out of the final pack, or filter at the query layer before ranking
ever sees unauthorized data. The first is easier to bolt on later and is
exactly the kind of mistake that leaks content through slot-filling
heuristics, truncation logic, or a cache — any of which might retain or
surface a fragment of something the actor should never have seen.

## Decision
`AuthorizationService.filter_visible` is applied at the repository query
layer (`persistence/`), before graph traversal results are ranked and
before context-pack compilation runs (`docs/SECURITY.md`). Ranking and
compilation only ever see nodes the actor is already permitted to read.
Context-space membership is never treated as a source-access grant —
access is resolved from the node/evidence's own `acl_ref`. Derived
fragments inherit their source's ACL unchanged.

Fixture mode still runs this path, using simplified group maps
(`fixtures/authz/`), so the behavior is exercised in every test run, not
only in a hypothetical production configuration.

## Consequences
- No downstream code path (ranking, token-budget truncation, caching in
  `task_checkpoint`) can accidentally surface unauthorized content, because
  it never receives it.
- The acceptance test proving this (`docs/phases/PHASE-11.md`) is a
  permanent gate, not a one-time check — it must stay green.
- Revoking access or deleting a source object must propagate to
  `acl_ref` resolution promptly; this is a sync-path requirement, not
  purely an authorization-path one (`docs/SECURITY.md` "deletions and
  access revocation").
