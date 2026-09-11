"""node

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE node (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            layer               TEXT NOT NULL CHECK (layer IN ('BUSINESS','TECHNICAL','LOGICAL')),
            kind                TEXT NOT NULL,
            capability          TEXT NULL,
            name                TEXT NOT NULL,
            description         TEXT NULL,
            owners              JSONB NOT NULL DEFAULT '[]',
            source_system       TEXT NULL,
            source_instance_id  TEXT NULL,
            native_id           TEXT NULL,
            parent_id           UUID NULL REFERENCES node(id),
            path                LTREE NOT NULL,
            status              TEXT NOT NULL DEFAULT 'ACTIVE',
            version             INT NOT NULL DEFAULT 1,
            source_version      TEXT NULL,
            content_hash        TEXT NULL,
            acl_ref             JSONB NOT NULL DEFAULT '{}',
            attributes          JSONB NOT NULL DEFAULT '{}',
            first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at          TIMESTAMPTZ NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_node_technical_identity
            ON node (source_system, source_instance_id, native_id)
            WHERE layer = 'TECHNICAL'
        """
    )
    op.execute("CREATE INDEX ix_node_path_gist ON node USING GIST (path)")
    op.execute("CREATE INDEX ix_node_parent ON node (parent_id)")
    op.execute("CREATE INDEX ix_node_layer_kind ON node (layer, kind)")
    op.execute(
        "CREATE INDEX ix_node_capability ON node (capability) WHERE capability IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_node_not_deleted ON node (id) WHERE deleted_at IS NULL")


def downgrade() -> None:
    op.execute("DROP TABLE node")
