from uuid import uuid4

from context_fabric.domain.context_pack import (
    ContextPack,
    ContextPackItem,
    ExpansionHandle,
    FreshnessEntry,
)
from context_fabric.domain.evidence import Evidence


def test_context_pack_item_traces_to_evidence(now):
    node_id = uuid4()
    evidence = Evidence(
        id=uuid4(),
        node_id=node_id,
        source_system="azure_devops",
        source_instance_id="ado-acme",
        native_id="312",
        uri="https://dev.azure.com/acme/_workitems/edit/312",
        retrieved_at=now,
    )
    item = ContextPackItem(
        node_id=node_id,
        evidence_id=evidence.id,
        kind="WORK_ITEM",
        name="Add SSO callback",
    )
    pack = ContextPack(
        approved_requirements=[item],
        evidence=[evidence],
        freshness=[
            FreshnessEntry(evidence_id=evidence.id, age_days=1.0, exceeds_max_age=False)
        ],
        created_at=now,
    )

    # Every item's evidence_id must be present in the pack's evidence list —
    # the traceability guarantee docs/MCP.md requires (enforced structurally
    # by the retrieval compiler in Phase 10; this test proves the shape
    # supports the invariant).
    evidence_ids = {e.id for e in pack.evidence}
    assert all(i.evidence_id in evidence_ids for i in pack.approved_requirements)


def test_context_pack_defaults_are_empty(now):
    pack = ContextPack(created_at=now)
    assert pack.hard_constraints == []
    assert pack.conflicts == []
    assert pack.expansion_handles == []


def test_expansion_handle_shape():
    handle = ExpansionHandle(evidence_id=uuid4(), reason="token_budget")
    assert handle.reason == "token_budget"
