from uuid import uuid4

import pytest
from pydantic import ValidationError

from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType


def test_edge_constructs_with_defaults(now):
    edge = Edge(
        src_id=uuid4(),
        dst_id=uuid4(),
        type=EdgeType.CONTAINS,
        origin=EdgeOrigin.SYNC_STRUCTURAL,
        first_seen_at=now,
        last_seen_at=now,
    )
    assert edge.confidence == 1.0
    assert edge.state is EdgeState.ACTIVE
    assert edge.evidence_id is None


def test_extracted_edge_can_be_proposed(now):
    edge = Edge(
        src_id=uuid4(),
        dst_id=uuid4(),
        type=EdgeType.MENTIONS,
        origin=EdgeOrigin.SYNC_EXTRACTED,
        state=EdgeState.PROPOSED,
        confidence=0.6,
        first_seen_at=now,
        last_seen_at=now,
    )
    assert edge.state is EdgeState.PROPOSED
    assert edge.confidence == 0.6


def test_confidence_out_of_range_rejected(now):
    with pytest.raises(ValidationError):
        Edge(
            src_id=uuid4(),
            dst_id=uuid4(),
            type=EdgeType.RELATED_TO,
            origin=EdgeOrigin.HUMAN,
            confidence=1.5,
            first_seen_at=now,
            last_seen_at=now,
        )
