from uuid import uuid4

from context_fabric.domain.evidence import Evidence


def test_evidence_constructs(now):
    ev = Evidence(
        node_id=uuid4(),
        source_system="azure_devops",
        source_instance_id="ado-acme",
        native_id="312",
        uri="https://dev.azure.com/acme/TalentFlow/_workitems/edit/312",
        retrieved_at=now,
    )
    assert ev.acl_ref == {}
    assert ev.source_version is None
