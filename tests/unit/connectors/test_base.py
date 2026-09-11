from pathlib import Path

import httpx
import pytest
import structlog

from context_fabric.connectors.base import (
    FixtureConnectorBase,
    LiveConnectorBase,
    correlate,
)
from context_fabric.domain.connector_types import SourceObject
from context_fabric.domain.errors import (
    AuthError,
    NotFound,
    Permanent,
    RateLimited,
    SchemaDrift,
    Transient,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# FixtureConnectorBase
# ---------------------------------------------------------------------------


class _FakeFixtureConnector(FixtureConnectorBase):
    source_system = "fake_source"


@pytest.fixture
def fixture_connector() -> _FakeFixtureConnector:
    return _FakeFixtureConnector(fixtures_dir=FIXTURES_DIR)


def test_load_json_returns_parsed_data(fixture_connector):
    data = fixture_connector.load_json("sample.json")
    assert len(data) == 2
    assert data[0]["native_id"] == "1"


def test_load_json_missing_file_raises_not_found(fixture_connector):
    with pytest.raises(NotFound) as exc_info:
        fixture_connector.load_json("does_not_exist.json")
    assert exc_info.value.category.value == "NOT_FOUND"
    assert exc_info.value.source_system == "fake_source"


def test_load_json_malformed_raises_schema_drift(fixture_connector):
    with pytest.raises(SchemaDrift):
        fixture_connector.load_json("malformed.json")


def test_parse_many_returns_domain_objects(fixture_connector):
    raw = fixture_connector.load_json("sample.json")
    items = fixture_connector.parse_many(SourceObject, raw)
    assert all(isinstance(i, SourceObject) for i in items)
    assert items[0].name == "Alpha"


def test_parse_many_raises_schema_drift_naming_offending_item(fixture_connector):
    raw = fixture_connector.load_json("invalid_items.json")
    with pytest.raises(SchemaDrift, match="fixture item 1"):
        fixture_connector.parse_many(SourceObject, raw)


def test_find_by_native_id_found(fixture_connector):
    raw = fixture_connector.load_json("sample.json")
    items = fixture_connector.parse_many(SourceObject, raw)
    found = fixture_connector.find_by_native_id(items, "2")
    assert found.name == "Beta"


def test_find_by_native_id_missing_raises_not_found(fixture_connector):
    raw = fixture_connector.load_json("sample.json")
    items = fixture_connector.parse_many(SourceObject, raw)
    with pytest.raises(NotFound, match="999"):
        fixture_connector.find_by_native_id(items, "999")


# ---------------------------------------------------------------------------
# LiveConnectorBase — retry behavior
# ---------------------------------------------------------------------------


class _FakeLiveConnector(LiveConnectorBase):
    source_system = "fake_source"


@pytest.fixture
def live_connector() -> _FakeLiveConnector:
    # Near-zero backoff so retry tests run fast and deterministically.
    return _FakeLiveConnector(
        "https://example.invalid",
        max_attempts=3,
        backoff_multiplier=0.001,
        backoff_max=0.01,
    )


async def test_call_with_retry_does_not_retry_permanent(live_connector):
    calls = 0

    async def always_permanent():
        nonlocal calls
        calls += 1
        raise Permanent("nope", source_system="fake_source")

    with pytest.raises(Permanent):
        await live_connector.call_with_retry(always_permanent)
    assert calls == 1


async def test_call_with_retry_does_not_retry_auth_error(live_connector):
    calls = 0

    async def always_auth_error():
        nonlocal calls
        calls += 1
        raise AuthError("bad creds", source_system="fake_source")

    with pytest.raises(AuthError):
        await live_connector.call_with_retry(always_auth_error)
    assert calls == 1


async def test_call_with_retry_does_not_retry_not_found(live_connector):
    calls = 0

    async def always_not_found():
        nonlocal calls
        calls += 1
        raise NotFound("gone", source_system="fake_source")

    with pytest.raises(NotFound):
        await live_connector.call_with_retry(always_not_found)
    assert calls == 1


async def test_call_with_retry_retries_transient_up_to_max_attempts(live_connector):
    calls = 0

    async def always_transient():
        nonlocal calls
        calls += 1
        raise Transient("network blip", source_system="fake_source")

    with pytest.raises(Transient):
        await live_connector.call_with_retry(always_transient)
    assert calls == 3  # max_attempts


async def test_call_with_retry_retries_rate_limited_then_succeeds(live_connector):
    calls = 0

    async def fails_once_then_succeeds():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RateLimited("slow down", source_system="fake_source", retry_after_seconds=0.001)
        return "ok"

    result = await live_connector.call_with_retry(fails_once_then_succeeds)
    assert result == "ok"
    assert calls == 2


# ---------------------------------------------------------------------------
# LiveConnectorBase — status code -> error category mapping
# ---------------------------------------------------------------------------


def _response(status: int, headers: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://example.invalid/thing")
    return httpx.Response(status, headers=headers or {}, request=request)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthError),
        (403, AuthError),
        (404, NotFound),
        (429, RateLimited),
        (500, Transient),
        (503, Transient),
        (400, Permanent),
    ],
)
def test_raise_for_status_category(live_connector, status, expected):
    with pytest.raises(expected):
        live_connector.raise_for_status_category(_response(status))


def test_raise_for_status_category_captures_retry_after(live_connector):
    with pytest.raises(RateLimited) as exc_info:
        live_connector.raise_for_status_category(_response(429, headers={"Retry-After": "30"}))
    assert exc_info.value.retry_after_seconds == 30.0


def test_raise_for_status_category_ok_status_raises_nothing(live_connector):
    live_connector.raise_for_status_category(_response(200))


# ---------------------------------------------------------------------------
# correlate
# ---------------------------------------------------------------------------


def test_correlate_context_manager_binds_and_unbinds():
    assert "correlation_id" not in structlog.contextvars.get_contextvars()
    with correlate("run-123") as cid:
        assert cid == "run-123"
        assert structlog.contextvars.get_contextvars()["correlation_id"] == "run-123"
    assert "correlation_id" not in structlog.contextvars.get_contextvars()


def test_correlate_generates_id_when_none_given():
    with correlate() as cid:
        assert cid  # non-empty, generated


def test_correlate_inherits_existing_bound_id_instead_of_overwriting():
    with correlate("outer-id"):
        with correlate() as inner_cid:
            assert inner_cid == "outer-id"


async def test_correlate_decorator_propagates_into_log_records():
    logger = structlog.get_logger()

    @correlate()
    async def do_work():
        logger.info("work.done")

    with structlog.testing.capture_logs(
        processors=[structlog.contextvars.merge_contextvars]
    ) as captured:
        await do_work()

    assert len(captured) == 1
    assert captured[0]["event"] == "work.done"
    assert "correlation_id" in captured[0]
    assert captured[0]["correlation_id"]


async def test_correlate_decorator_reuses_outer_run_id():
    logger = structlog.get_logger()

    @correlate()
    async def inner():
        logger.info("inner.log")

    async def orchestrator():
        with correlate("sync-run-42"):
            await inner()

    with structlog.testing.capture_logs(
        processors=[structlog.contextvars.merge_contextvars]
    ) as captured:
        await orchestrator()

    assert captured[0]["correlation_id"] == "sync-run-42"
