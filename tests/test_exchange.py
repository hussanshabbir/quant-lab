"""Tests for src.calendar.exchange.CMEEquityCalendar.

Fixture dates are chosen to exercise: a full holiday (Christmas), an
early-close day (Thanksgiving), a plain trading day, and a weekend.
"""

import datetime as dt

import pytest

from src.calendar.exchange import CMEEquityCalendar


@pytest.fixture(scope="module")
def calendar() -> CMEEquityCalendar:
    return CMEEquityCalendar()


def test_christmas_is_not_a_trading_day(calendar):
    assert calendar.is_trading_day(dt.date(2025, 12, 25)) is False


def test_christmas_has_no_trading_bounds(calendar):
    assert calendar.trading_day_bounds(dt.date(2025, 12, 25)) is None


def test_weekend_is_not_a_trading_day(calendar):
    # Saturday, no Sunday-evening session has opened into it yet.
    assert calendar.is_trading_day(dt.date(2026, 1, 17)) is False


def test_thanksgiving_is_a_trading_day_with_early_close(calendar):
    day = calendar.trading_day_bounds(dt.date(2025, 11, 27))
    assert day is not None
    assert day.is_early_close is True
    # Actual CME close: 12:00 CT == 18:00 UTC, well before the standard 22:00 UTC.
    assert day.close_utc.hour == 18


def test_day_after_thanksgiving_is_also_early_close(calendar):
    day = calendar.trading_day_bounds(dt.date(2025, 11, 28))
    assert day is not None
    assert day.is_early_close is True


def test_ordinary_trading_day_is_not_early_close(calendar):
    # A plain midweek January day with no adjacent holiday.
    day = calendar.trading_day_bounds(dt.date(2026, 1, 15))
    assert day is not None
    assert day.is_early_close is False
    # Standard close: 16:00 CT == 22:00 UTC in winter (CST, UTC-6).
    assert day.close_utc.hour == 22


def test_holidays_lists_full_closures_only(calendar):
    # Dec 2025 window covering Christmas (full closure) and Thanksgiving
    # week (early closes, which must NOT appear in this list).
    holidays = calendar.holidays(dt.date(2025, 11, 24), dt.date(2025, 12, 26))
    assert dt.date(2025, 12, 25) in holidays
    assert dt.date(2025, 11, 27) not in holidays
    assert dt.date(2025, 11, 28) not in holidays


def test_trading_days_excludes_holidays_and_weekends(calendar):
    days = calendar.trading_days(dt.date(2025, 12, 24), dt.date(2025, 12, 26))
    assert dt.date(2025, 12, 24) in days
    assert dt.date(2025, 12, 25) not in days
    assert dt.date(2025, 12, 26) in days
