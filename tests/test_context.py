"""Tests for shoal.core.context — context propagation helpers."""

from __future__ import annotations

import logging

from shoal.core.context import (
    ContextFilter,
    generate_request_id,
    get_request_id,
    get_session_id,
    set_request_id,
    set_session_id,
)


class TestContextVars:
    """Test get/set of context variables."""

    def test_default_session_id_empty(self) -> None:
        # Defaults should be empty string (may be set from prior tests, so reset)
        set_session_id("")
        assert get_session_id() == ""

    def test_set_and_get_session_id(self) -> None:
        set_session_id("abc123")
        assert get_session_id() == "abc123"
        set_session_id("")  # clean up

    def test_set_and_get_request_id(self) -> None:
        set_request_id("req-001")
        assert get_request_id() == "req-001"
        set_request_id("")  # clean up


class TestGenerateRequestId:
    def test_returns_8_char_hex(self) -> None:
        rid = generate_request_id()
        assert len(rid) == 8
        int(rid, 16)  # should not raise

    def test_uniqueness(self) -> None:
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100


class TestContextFilter:
    def test_filter_injects_fields(self) -> None:
        set_session_id("sid-test")
        set_request_id("rid-test")

        f = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        result = f.filter(record)
        assert result is True
        assert record.session_id == "sid-test"  # type: ignore[attr-defined]
        assert record.request_id == "rid-test"  # type: ignore[attr-defined]

        # clean up
        set_session_id("")
        set_request_id("")

    def test_filter_empty_defaults(self) -> None:
        set_session_id("")
        set_request_id("")

        f = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        f.filter(record)
        assert record.session_id == ""  # type: ignore[attr-defined]
        assert record.request_id == ""  # type: ignore[attr-defined]
