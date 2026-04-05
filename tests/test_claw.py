"""Tests for the Shoal claw scheduling and trigger system."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shoal.models.claw import (
    ExecutionStatus,
    TriggerDef,
    TriggerExecution,
    TriggerKind,
)
from shoal.models.config.general import ClawConfig
from shoal.services.claw_daemon import ClawDaemon, cron_matches

# ---------------------------------------------------------------------------
# Cron matcher tests
# ---------------------------------------------------------------------------


class TestCronMatches:
    """Test the hand-rolled 5-field cron matcher."""

    def test_all_stars(self) -> None:
        dt = datetime(2026, 4, 3, 14, 30, tzinfo=UTC)
        assert cron_matches("* * * * *", dt) is True

    def test_exact_minute_hour(self) -> None:
        dt = datetime(2026, 4, 3, 14, 30, tzinfo=UTC)
        assert cron_matches("30 14 * * *", dt) is True
        assert cron_matches("31 14 * * *", dt) is False

    def test_midnight_daily(self) -> None:
        dt = datetime(2026, 4, 3, 0, 0, tzinfo=UTC)
        assert cron_matches("0 0 * * *", dt) is True

    def test_range(self) -> None:
        dt = datetime(2026, 4, 3, 10, 0, tzinfo=UTC)
        assert cron_matches("0 9-17 * * *", dt) is True
        assert cron_matches("0 18-23 * * *", dt) is False

    def test_step(self) -> None:
        dt = datetime(2026, 4, 3, 0, 0, tzinfo=UTC)
        assert cron_matches("*/15 * * * *", dt) is True
        dt2 = datetime(2026, 4, 3, 0, 7, tzinfo=UTC)
        assert cron_matches("*/15 * * * *", dt2) is False

    def test_list(self) -> None:
        dt = datetime(2026, 4, 3, 10, 0, tzinfo=UTC)
        assert cron_matches("0 8,10,12 * * *", dt) is True
        assert cron_matches("0 9,11,13 * * *", dt) is False

    def test_day_of_week(self) -> None:
        # 2026-04-03 is a Friday = weekday() == 4
        dt = datetime(2026, 4, 3, 0, 0, tzinfo=UTC)
        assert cron_matches("0 0 * * 4", dt) is True
        assert cron_matches("0 0 * * 1", dt) is False

    def test_specific_month_day(self) -> None:
        dt = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
        assert cron_matches("0 9 1 * *", dt) is True
        assert cron_matches("0 9 2 * *", dt) is False

    def test_invalid_format(self) -> None:
        dt = datetime(2026, 4, 3, 0, 0, tzinfo=UTC)
        assert cron_matches("invalid", dt) is False
        assert cron_matches("* * *", dt) is False


# ---------------------------------------------------------------------------
# TriggerDef model tests
# ---------------------------------------------------------------------------


class TestTriggerDef:
    """Test TriggerDef Pydantic model."""

    def test_create_cron_trigger(self) -> None:
        t = TriggerDef(
            id="abc123",
            name="nightly-sec",
            kind=TriggerKind.cron,
            template="shoal-sec",
            cron_expr="0 0 * * *",
        )
        assert t.enabled is True
        assert t.fire_count == 0
        assert t.max_concurrent == 1

    def test_create_event_trigger(self) -> None:
        t = TriggerDef(
            id="def456",
            name="auto-review",
            kind=TriggerKind.event,
            template="shoal-reviewer",
            event_name="session_completed",
            event_filter={"mode": "implementer"},
        )
        assert t.event_filter == {"mode": "implementer"}

    def test_create_timer_trigger(self) -> None:
        t = TriggerDef(
            id="ghi789",
            name="delayed-review",
            kind=TriggerKind.timer,
            template="shoal-reviewer",
            fire_at="2026-04-04T09:00:00+00:00",
        )
        assert t.kind == TriggerKind.timer

    def test_roundtrip_json(self) -> None:
        t = TriggerDef(
            id="abc123",
            name="test",
            kind=TriggerKind.webhook,
            template="shoal-impl",
            tags=["ci", "nightly"],
        )
        json_str = t.model_dump_json()
        restored = TriggerDef.model_validate_json(json_str)
        assert restored.name == "test"
        assert restored.tags == ["ci", "nightly"]


# ---------------------------------------------------------------------------
# DB CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_crud(tmp_path: Any) -> None:
    """Test save/get/list/delete trigger via ShoalDB."""
    from shoal.core.db import ShoalDB

    db = ShoalDB(tmp_path / "test.db")
    await db.connect()

    trigger = TriggerDef(
        id="t1",
        name="test-trigger",
        kind=TriggerKind.cron,
        template="shoal-sec",
        cron_expr="0 0 * * *",
        created_at=datetime.now(UTC).isoformat(),
    )

    await db.save_trigger(trigger)

    # Get
    fetched = await db.get_trigger("test-trigger")
    assert fetched is not None
    assert fetched.id == "t1"
    assert fetched.cron_expr == "0 0 * * *"

    # List
    all_triggers = await db.list_triggers()
    assert len(all_triggers) == 1

    # Update
    trigger.fire_count = 5
    await db.save_trigger(trigger)
    updated = await db.get_trigger("test-trigger")
    assert updated is not None
    assert updated.fire_count == 5

    # Delete
    await db.delete_trigger("test-trigger")
    gone = await db.get_trigger("test-trigger")
    assert gone is None

    await db.close()


@pytest.mark.asyncio
async def test_execution_crud(tmp_path: Any) -> None:
    """Test save/list/update execution via ShoalDB."""
    from shoal.core.db import ShoalDB

    db = ShoalDB(tmp_path / "test.db")
    await db.connect()

    ex = TriggerExecution(
        id="e1",
        trigger_id="t1",
        trigger_name="test-trigger",
        session_id="s1",
        session_name="sec-120000",
        started_at=datetime.now(UTC).isoformat(),
    )
    await db.save_execution(ex)

    # List
    execs = await db.list_executions("t1")
    assert len(execs) == 1
    assert execs[0].session_name == "sec-120000"

    # Count active
    active = await db.count_active_executions("t1")
    assert active == 1

    # Update status
    await db.update_execution_status("e1", ExecutionStatus.completed, datetime.now(UTC).isoformat())
    active_after = await db.count_active_executions("t1")
    assert active_after == 0

    await db.close()


# ---------------------------------------------------------------------------
# ClawConfig tests
# ---------------------------------------------------------------------------


class TestClawConfig:
    """Test ClawConfig defaults."""

    def test_defaults(self) -> None:
        cfg = ClawConfig()
        assert cfg.enabled is False
        assert cfg.poll_interval == 30
        assert cfg.log_file == "claw.log"

    def test_on_shoal_config(self) -> None:
        from shoal.models.config.general import ShoalConfig

        cfg = ShoalConfig()
        assert isinstance(cfg.claw, ClawConfig)
        assert cfg.claw.enabled is False


# ---------------------------------------------------------------------------
# Daemon logic tests
# ---------------------------------------------------------------------------


class TestClawDaemon:
    """Test ClawDaemon methods without actually spawning sessions."""

    def test_event_filter_matches_simple(self) -> None:
        assert ClawDaemon._event_filter_matches({"mode": "implementer"}, {"mode": "implementer"})
        assert not ClawDaemon._event_filter_matches({"mode": "reviewer"}, {"mode": "implementer"})

    def test_event_filter_matches_empty(self) -> None:
        assert ClawDaemon._event_filter_matches({}, {"anything": "value"})

    def test_event_filter_matches_nested_session(self) -> None:
        """Filter can match attributes on a session object in kwargs."""
        session = MagicMock()
        session.mode = "implementer"
        assert ClawDaemon._event_filter_matches({"mode": "implementer"}, {"session": session})

    @pytest.mark.asyncio
    async def test_should_fire_respects_cooldown(self, tmp_path: Any) -> None:
        from shoal.core.db import ShoalDB

        db = ShoalDB(tmp_path / "test.db")
        await db.connect()

        trigger = TriggerDef(
            id="t1",
            name="test",
            kind=TriggerKind.cron,
            template="shoal-sec",
            cooldown_seconds=300,
            last_fired_at=datetime.now(UTC).isoformat(),
        )

        daemon = ClawDaemon(ClawConfig())
        with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
            result = await daemon._should_fire(trigger, datetime.now(UTC))
        assert result is False

        await db.close()

    @pytest.mark.asyncio
    async def test_should_fire_allows_after_cooldown(self, tmp_path: Any) -> None:
        from shoal.core.db import ShoalDB

        db = ShoalDB(tmp_path / "test.db")
        await db.connect()

        old_time = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        trigger = TriggerDef(
            id="t1",
            name="test",
            kind=TriggerKind.cron,
            template="shoal-sec",
            cooldown_seconds=300,
            last_fired_at=old_time,
        )

        daemon = ClawDaemon(ClawConfig())
        with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
            result = await daemon._should_fire(trigger, datetime.now(UTC))
        assert result is True

        await db.close()

    @pytest.mark.asyncio
    async def test_should_fire_respects_max_concurrent(self, tmp_path: Any) -> None:
        from shoal.core.db import ShoalDB

        db = ShoalDB(tmp_path / "test.db")
        await db.connect()

        trigger = TriggerDef(
            id="t1",
            name="test",
            kind=TriggerKind.cron,
            template="shoal-sec",
            max_concurrent=1,
        )

        # Add a running execution
        ex = TriggerExecution(
            id="e1",
            trigger_id="t1",
            trigger_name="test",
            session_id="s1",
            session_name="sec-1",
            started_at=datetime.now(UTC).isoformat(),
        )
        await db.save_execution(ex)

        daemon = ClawDaemon(ClawConfig())
        with patch("shoal.core.db.get_db", new_callable=AsyncMock, return_value=db):
            result = await daemon._should_fire(trigger, datetime.now(UTC))
        assert result is False

        await db.close()
