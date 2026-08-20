"""Tests for src.calendar.timestamps."""

import datetime as dt

import pandas as pd
import pytest

from src.calendar.exchange import CMEEquityCalendar
from src.calendar.timestamps import (
    NoTradingDayFoundError,
    sessions_containing_timestamp,
    to_utc_timestamp,
    trading_date_for_timestamp,
)


@pytest.fixture(scope="module")
def calendar() -> CMEEquityCalendar:
    return CMEEquityCalendar()


def test_naive_timestamp_without_source_tz_raises():
    with pytest.raises(ValueError):
        to_utc_timestamp(dt.datetime(2026, 1, 15, 9, 30))


def test_naive_timestamp_with_source_tz_converts_correctly():
    result = to_utc_timestamp(dt.datetime(2026, 1, 15, 9, 30), source_tz="America/New_York")
    assert result == pd.Timestamp("2026-01-15 14:30:00", tz="UTC")


def test_already_aware_timestamp_is_converted_to_utc():
    raw = pd.Timestamp("2026-01-15 09:30:00", tz="America/New_York")
    result = to_utc_timestamp(raw)
    assert result == pd.Timestamp("2026-01-15 14:30:00", tz="UTC")


def test_trading_date_for_ordinary_daytime_timestamp(calendar):
    ts = pd.Timestamp("2026-01-15 14:30:00", tz="UTC")  # NY session open
    assert trading_date_for_timestamp(ts, calendar) == dt.date(2026, 1, 15)


def test_sunday_evening_open_belongs_to_mondays_trading_date(calendar):
    # Globex opens Sunday 17:00 CT == 23:00 UTC; that session belongs to Monday.
    ts = pd.Timestamp("2026-01-18 23:30:00", tz="UTC")  # Sunday 2026-01-18 evening
    assert trading_date_for_timestamp(ts, calendar) == dt.date(2026, 1, 19)


def test_timestamp_during_full_holiday_raises(calendar):
    ts = pd.Timestamp("2025-12-25 18:00:00", tz="UTC")  # Christmas, full closure
    with pytest.raises(NoTradingDayFoundError):
        trading_date_for_timestamp(ts, calendar)


def test_sessions_containing_timestamp_single_session(calendar):
    ts = pd.Timestamp("2026-01-15 02:00:00", tz="UTC")  # inside Asia 00:00-06:00
    sessions = sessions_containing_timestamp(ts, calendar)
    assert [s.name for s in sessions] == ["asia"]


def test_sessions_containing_timestamp_london_new_york_overlap(calendar):
    # Europe 08:00-16:30 UTC, New York 14:30-21:00 UTC (winter) -> overlap 14:30-16:30.
    ts = pd.Timestamp("2026-01-15 15:00:00", tz="UTC")
    sessions = sessions_containing_timestamp(ts, calendar)
    assert {s.name for s in sessions} == {"europe", "new_york"}


def test_sessions_containing_timestamp_gap_returns_empty(calendar):
    # 06:30 UTC: after Asia close (06:00), before Europe open (08:00).
    ts = pd.Timestamp("2026-01-15 06:30:00", tz="UTC")
    assert sessions_containing_timestamp(ts, calendar) == []
