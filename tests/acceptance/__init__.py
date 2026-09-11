"""Acceptance tests: end-to-end proofs of the gates named throughout
docs/phases/*.md — idempotent sync (same fixture twice => zero net graph
change), the connector anti-leakage test (no vendor payload shape crosses
into retrieval), and the authorization gate (unauthorized evidence never
appears in a compiled context pack). These are the tests referenced by each
phase's "acceptance criteria" section.
"""
