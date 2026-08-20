"""Regression tests pinning known, currently-accepted quirks of the
underlying pandas_market_calendars data.

These are NOT tests of our own logic -- they pin third-party library
behavior we depend on (or, in one case, a known library defect we've
consciously chosen to defer rather than fix). See docs/known_gaps.md for
the full writeup, rationale, and the explicit trigger condition for
revisiting each one. If either test here starts failing after a
`pandas_market_calendars` version bump, that's a signal to re-read
docs/known_gaps.md before touching anything -- it likely means upstream
changed behavior we were relying on (good or bad).
"""

import datetime as dt

import pytest

from src.calendar.exchange import CMEEquityCalendar


@pytest.fixture(scope="module")
def calendar() -> CMEEquityCalendar:
    return CMEEquityCalendar()


def test_jan_9_2025_ad_hoc_closure_is_a_known_library_gap(calendar):
    """KNOWN GAP (docs/known_gaps.md, Gap 1) -- deliberately deferred.

    CME actually kept ES trading overnight on 2025-01-09 (National Day of
    Mourning for President Carter), closing early at 08:30 CT rather than
    not trading at all. CME_Equity currently treats the entire day as a
    full holiday, which is wrong. This test pins that WRONG behavior on
    purpose: if it ever starts failing, `pandas_market_calendars` has
    fixed the gap upstream -- re-read docs/known_gaps.md Gap 1 and update
    both the test and the doc rather than just deleting this test.
    """
    assert calendar.is_trading_day(dt.date(2025, 1, 9)) is False
    assert calendar.trading_day_bounds(dt.date(2025, 1, 9)) is None


def test_2005_2012_hours_regime_is_correctly_modeled(calendar):
    """Pins CME_Equity's correct modeling of the real 2005-09 to 2012-11
    shortened electronic-hours regime (open 15:30 CT, close 15:15 CT --
    not today's 17:00/16:00). See docs/known_gaps.md Gap 2: this is the
    reason we use CME_Equity rather than the library's other CME
    equity-index calendar, "CME Globex Equity", which gets this wrong.
    """
    day = calendar.trading_day_bounds(dt.date(2008, 6, 3))
    assert day is not None
    open_local = day.open_utc.tz_convert("America/Chicago")
    close_local = day.close_utc.tz_convert("America/Chicago")
    assert open_local.time() == dt.time(15, 30)
    assert close_local.time() == dt.time(15, 15)
