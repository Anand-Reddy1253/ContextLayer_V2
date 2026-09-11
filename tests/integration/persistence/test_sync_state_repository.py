from context_fabric.domain.enums import SyncStatus
from context_fabric.domain.sync import SyncState
from context_fabric.persistence.repositories.sync_state import SyncStateRepository


async def test_upsert_creates_then_updates(db_session):
    repo = SyncStateRepository(db_session)

    first = await repo.upsert(
        SyncState(source_system="azure_devops", scope_id="TalentFlow", cursor="c1")
    )
    assert first.status is SyncStatus.PENDING

    second = await repo.upsert(
        SyncState(
            source_system="azure_devops",
            scope_id="TalentFlow",
            cursor="c2",
            status=SyncStatus.SUCCEEDED,
        )
    )
    assert second.cursor == "c2"
    assert second.status is SyncStatus.SUCCEEDED

    fetched = await repo.get("azure_devops", "TalentFlow")
    assert fetched.cursor == "c2"


async def test_get_missing_returns_none(db_session):
    repo = SyncStateRepository(db_session)
    assert await repo.get("github", "does-not-exist") is None
