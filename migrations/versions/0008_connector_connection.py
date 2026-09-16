"""connector_connection

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    id_type = "TEXT PRIMARY KEY" if is_sqlite else "UUID PRIMARY KEY DEFAULT gen_random_uuid()"
    json_type = "TEXT" if is_sqlite else "JSONB"
    blob_type = "BLOB" if is_sqlite else "BYTEA"
    ts_type = "TEXT" if is_sqlite else "TIMESTAMPTZ"
    ts_default = "DEFAULT CURRENT_TIMESTAMP" if is_sqlite else "DEFAULT now()"

    op.execute(
        f"""
        CREATE TABLE connector_connection (
            id                  {id_type},
            source_system       TEXT NOT NULL,
            instance_id         TEXT NOT NULL,
            display_name        TEXT NOT NULL,
            mode                TEXT NOT NULL DEFAULT 'fixture',
            config              {json_type} NOT NULL DEFAULT '{{}}',
            credential_ciphertext {blob_type} NULL,
            created_at          {ts_type} NOT NULL {ts_default},
            updated_at          {ts_type} NOT NULL {ts_default}
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_connector_connection_identity
            ON connector_connection (source_system, instance_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE connector_connection")
