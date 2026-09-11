"""Authorization.

AuthorizationService protocol: `can_read(actor, acl_ref)` and
`filter_visible(actor, nodes)`. Applied at the repository query layer,
before ranking and before context-pack compilation — never as a
post-filter on already-compiled results (docs/SECURITY.md).

Fixture mode resolves actor -> groups -> allowed acl_refs from
fixtures/authz/*.yaml. Context-space membership never implies source
access; access is always resolved from the evidence's own acl_ref, which
derived fragments inherit unchanged from their source node.

Depends on domain/, persistence/. Implemented in Phase 11
(docs/phases/PHASE-11.md), proven by an acceptance test that unauthorized
evidence never appears in a context pack.
"""
