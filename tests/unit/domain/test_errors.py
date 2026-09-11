import pytest

from context_fabric.domain.enums import ErrorCategory
from context_fabric.domain.errors import (
    AuthError,
    ConnectorError,
    NotFound,
    Permanent,
    RateLimited,
    SchemaDrift,
    Transient,
)


@pytest.mark.parametrize(
    ("error_cls", "expected_category"),
    [
        (AuthError, ErrorCategory.AUTH),
        (RateLimited, ErrorCategory.RATE_LIMITED),
        (NotFound, ErrorCategory.NOT_FOUND),
        (Transient, ErrorCategory.TRANSIENT),
        (Permanent, ErrorCategory.PERMANENT),
        (SchemaDrift, ErrorCategory.SCHEMA_DRIFT),
    ],
)
def test_error_category_matches(error_cls, expected_category):
    err = error_cls("boom", source_system="azure_devops")
    assert err.category is expected_category
    assert err.source_system == "azure_devops"
    assert isinstance(err, ConnectorError)


def test_rate_limited_carries_retry_after():
    err = RateLimited("slow down", retry_after_seconds=30.0)
    assert err.retry_after_seconds == 30.0


def test_callers_can_branch_on_category_not_message():
    try:
        raise RateLimited("vendor said 429")
    except ConnectorError as err:
        assert err.category is ErrorCategory.RATE_LIMITED
