import pytest
from sqlalchemy.exc import IntegrityError

from context_fabric.persistence.repositories.connector_connection import (
    ConnectorConnectionRepository,
)


async def test_create_and_get_never_exposes_ciphertext(db_session, now):
    repo = ConnectorConnectionRepository(db_session)

    created = await repo.create(
        source_system="azure_devops",
        instance_id="ado-acme",
        display_name="ACME Azure DevOps",
        mode="fixture",
        config={"org_url": "https://dev.azure.com/acme"},
        credential_ciphertext=b"\x00\x01encrypted-bytes",
        now=now,
    )

    assert not hasattr(created, "credential_ciphertext")

    fetched = await repo.get(created.id)
    assert fetched is not None
    assert not hasattr(fetched, "credential_ciphertext")
    assert fetched.config == {"org_url": "https://dev.azure.com/acme"}


async def test_identity_uniqueness_enforced(db_session, now):
    repo = ConnectorConnectionRepository(db_session)
    await repo.create(
        source_system="github",
        instance_id="github-acme",
        display_name="ACME GitHub",
        mode="fixture",
        config={},
        credential_ciphertext=None,
        now=now,
    )
    with pytest.raises(IntegrityError):
        await repo.create(
            source_system="github",
            instance_id="github-acme",
            display_name="Duplicate",
            mode="fixture",
            config={},
            credential_ciphertext=None,
            now=now,
        )


async def test_get_by_identity(db_session, now):
    repo = ConnectorConnectionRepository(db_session)
    created = await repo.create(
        source_system="github",
        instance_id="github-acme",
        display_name="ACME GitHub",
        mode="fixture",
        config={},
        credential_ciphertext=None,
        now=now,
    )
    found = await repo.get_by_identity("github", "github-acme")
    assert found is not None
    assert found.id == created.id
