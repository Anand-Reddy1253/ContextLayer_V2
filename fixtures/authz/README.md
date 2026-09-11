# Authorization fixtures

Simplified ACL group maps used by `authorization/` in fixture mode (Phase
11, [../../docs/phases/PHASE-11.md](../../docs/phases/PHASE-11.md)) to
resolve `actor_id -> groups -> allowed acl_refs` without a real identity
provider.

Planned files:

```
fixtures/authz/
├── actors.yaml       # actor_id -> group memberships
└── acl_grants.yaml   # acl_ref -> groups permitted to read it
```

Must include at least one actor who is deliberately excluded from at least
one acl_ref referenced by fixtures/azure_devops/ or fixtures/github/ data —
this is the negative case the authorization acceptance test asserts on
(docs/SECURITY.md "Fixture tests must prove that unauthorized evidence is
excluded").
