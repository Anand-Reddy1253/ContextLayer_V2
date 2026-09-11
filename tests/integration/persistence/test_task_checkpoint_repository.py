from context_fabric.domain.checkpoint import TaskCheckpoint
from context_fabric.persistence.repositories.task_checkpoint import TaskCheckpointRepository


async def test_save_creates_then_updates(db_session, now):
    repo = TaskCheckpointRepository(db_session)

    first = await repo.save(
        TaskCheckpoint(task_ref="AB#312", stage="design", updated_at=now)
    )
    assert first.stage == "design"

    second = await repo.save(
        TaskCheckpoint(
            task_ref="AB#312",
            stage="implementation",
            completed_actions=["Read design doc"],
            files_changed=["src/sso/callback.py"],
            evidence_versions={"evidence-17": "rev-4"},
            updated_at=now,
        )
    )
    assert second.stage == "implementation"
    assert second.files_changed == ["src/sso/callback.py"]

    fetched = await repo.get("AB#312")
    assert fetched.stage == "implementation"
    assert fetched.evidence_versions == {"evidence-17": "rev-4"}


async def test_get_missing_returns_none(db_session):
    repo = TaskCheckpointRepository(db_session)
    assert await repo.get("AB#999") is None
