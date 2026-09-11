"""ConnectorConnection ORM mapping (docs/persistence.md
"connector_connection").

credential_ciphertext is never read back into a domain type by any
repository method outside of decrypt-for-connector-use — see
docs/SECURITY.md and persistence/repositories/connector_connection.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import LargeBinary, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from context_fabric.persistence.orm.base import Base


class ConnectorConnectionORM(Base):
    __tablename__ = "connector_connection"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    instance_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="fixture")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
