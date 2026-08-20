"""Tests for src.calendar.sessions.build_day_sessions.

Covers: an ordinary day, a full CME holiday (no sessions at all), an
early-close day (New York session gets clipped, Asia/Europe do not),
and the US/UK DST-mismatch window where the London-New York UTC gap
compresses from its usual 5 hours to 4 (US already sprang forward,
UK hasn't yet).
"""

import datetime as dt

import pytest

from src.calendar.exchange import CMEEquityCalendar
from src.calendar.sessions import build_day_sessions


@pytest.fixture(scope="module")
def calendar() -> CMEEquityCalendar:
    return CMEEquityCalendar()


def test_full_holiday_has_no_sessions(calendar):
    assert build_day_sessions(dt.date(2025, 12, 25), calendar) is None


def test_ordinary_day_has_three_unclipped_sessions(calendar):
    sessions = build_day_sessions(dt.date(2026, 1, 15), calendar)
    assert set(sessions) == {"asia", "europe", "new_york"}
    for session in sessions.values():
        assert session.was_clipped is False
        assert session.clip_reason is None

    # Winter (both US and UK on standard time): fixed, well-known UTC hours.
    assert sessions["asia"].utc_open.hour == 0
    assert sessions["asia"].utc_close.hour == 6
    assert sessions["europe"].utc_open.hour == 8
    assert sessions["new_york"].utc_open.hour == 14
    assert sessions["new_york"].utc_open.minute == 30


def test_early_close_clips_new_york_but_not_asia_or_europe(calendar):
    sessions = build_day_sessions(dt.date(2025, 11, 27), calendar)  # Thanksgiving
    assert sessions["new_york"].was_clipped is True
    assert sessions["new_york"].clip_reason == "clipped_to_globex_early_close"
    # Clipped close (12:00 CT == 18:00 UTC) is well before the nominal 16:00 ET close.
    assert sessions["new_york"].utc_close.hour == 18

    assert sessions["asia"].was_clipped is False
    assert sessions["europe"].was_clipped is False


def test_asia_session_has_no_dst_year_round(calendar):
    """Asia/Tokyo observes no DST, so Asia session UTC hours are constant
    across a US/UK DST transition, unlike Europe/New York."""
    winter = build_day_sessions(dt.date(2026, 1, 15), calendar)["asia"]
    summer = build_day_sessions(dt.date(2026, 7, 15), calendar)["asia"]
    assert winter.utc_open.hour == summer.utc_open.hour == 0
    assert winter.utc_close.hour == summer.utc_close.hour == 6


def test_us_uk_dst_mismatch_window_compresses_europe_new_york_gap(calendar):
    """2026: US DST begins Sun Mar 8, UK DST (BST) begins Sun Mar 29.

    Mar 9-28 is a window where America/New_York has already sprung
    forward (EDT, UTC-4) but Europe/London has not (still GMT, UTC+0).
    In that window the gap between the two sessions' open times
    compresses from the usual 5.5h wall-clock gap (9:30 ET vs 8:00
    London, normally 6.5h apart in UTC when both are on winter time,
    or ...) down by exactly one hour relative to a non-mismatched date,
    because only one side has moved its clock.
    """
    normal_winter = build_day_sessions(dt.date(2026, 1, 15), calendar)
    normal_summer = build_day_sessions(dt.date(2026, 7, 15), calendar)
    mismatch = build_day_sessions(dt.date(2026, 3, 16), calendar)  # inside the gap

    def gap_hours(day):
        return (day["new_york"].utc_open - day["europe"].utc_open).total_seconds() / 3600

    normal_winter_gap = gap_hours(normal_winter)
    normal_summer_gap = gap_hours(normal_summer)
    mismatch_gap = gap_hours(mismatch)

    # Both "normal" dates (both zones on the same DST regime) agree.
    assert normal_winter_gap == normal_summer_gap == 6.5

    # The mismatch date is exactly 1 hour tighter, because New York has
    # sprung forward and London has not.
    assert mismatch_gap == 5.5


def test_dst_transition_day_itself_is_a_normal_trading_day(calendar):
    """Mar 9 2026 (Monday) is the first US trading day after the US
    DST switch -- confirm session construction doesn't error or produce
    a nonsensical (e.g. negative-length) session across the switch."""
    sessions = build_day_sessions(dt.date(2026, 3, 9), calendar)
    ny = sessions["new_york"]
    assert ny.utc_close > ny.utc_open
    assert ny.utc_open.hour == 13  # EDT already in effect: 9:30 ET == 13:30 UTC
    assert ny.utc_open.minute == 30
