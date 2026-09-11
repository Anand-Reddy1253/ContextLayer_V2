from datetime import UTC, datetime

import pytest


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)
