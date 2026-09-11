from context_fabric.domain.checkpoint import TaskCheckpoint


def test_checkpoint_defaults(now):
    cp = TaskCheckpoint(task_ref="AB#312", stage="implementation", updated_at=now)
    assert cp.context_space_ids == []
    assert cp.evidence_versions == {}
    assert cp.repository_sha is None


def test_checkpoint_tracks_progress(now):
    cp = TaskCheckpoint(
        task_ref="AB#312",
        stage="implementation",
        objective="Wire up SSO callback",
        context_space_ids=["talentflow/identity"],
        completed_actions=["Read design doc"],
        files_changed=["src/sso/callback.py"],
        evidence_versions={"evidence-17": "rev-4"},
        repository_sha="abc123",
        updated_at=now,
    )
    assert cp.files_changed == ["src/sso/callback.py"]
    assert cp.evidence_versions["evidence-17"] == "rev-4"
