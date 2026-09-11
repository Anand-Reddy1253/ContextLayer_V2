from uuid import uuid4

from context_fabric.domain.context_space import Binding, ContextSpace
from context_fabric.domain.enums import Capability, EdgeOrigin


def test_context_space_with_bindings_constructs(now):
    space = ContextSpace(
        id="talentflow/identity",
        name="TalentFlow — Identity Squad",
        description="Identity and access management capability.",
        owners=["identity-squad-lead@acme.example"],
        product="talentflow",
        teams=["identity-squad"],
        services=["identity-service", "sso-gateway"],
        created_at=now,
        updated_at=now,
        business_node_id=uuid4(),
        bindings=[
            Binding(
                context_space_id="talentflow/identity",
                capability=Capability.CODE,
                source_system="github",
                source_instance_id="github-acme",
                native_container="acme-org/identity-service",
                created_at=now,
                updated_at=now,
            )
        ],
    )
    assert space.status == "active"
    assert len(space.bindings) == 1
    assert space.bindings[0].origin is EdgeOrigin.HUMAN
