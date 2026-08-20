"""Tests for src.calendar.session_geometry.compute_session_geometry.

All bar data here is synthetic and hand-labeled, built only to exercise
the geometry math and edge-case handling -- none of it is, or is meant
to resemble, real ES market data. See session_geometry.py's module
docstring for the scope boundary this module respects (no hypothesis
logic, ever) and the VWAP convention used.

Test-to-requirement mapping (14 explicit cases requested):
  1.  test_synthetic_session_known_ohlc
  2.  test_high_low_correctly_identified
  3.  test_open_is_first_chronological_bar
  4.  test_close_is_last_chronological_bar
  5.  test_volume_summed_correctly
  6.  test_vwap_calculated_correctly
  7.  test_high_low_timestamps_correct
  8.  test_zero_volume_bars_handled_explicitly
  9.  test_missing_bars_dont_alter_session_boundaries
  10. test_session_crossing_utc_midnight
  11. test_dst_transition_session_via_calendar_layer
  12. test_early_close_session_terminates_correctly
  13. test_empty_session_raises_explicitly
  14. test_duplicate_bars_do_not_silently_double_count
"""

import datetime as dt

import pandas as pd
import pytest

from src.calendar.exchange import CMEEquityCalendar
from src.calendar.session_geometry import (
    DuplicateBarsError,
    EmptySessionError,
    compute_session_geometry,
)
from src.calendar.sessions import SessionWindow, build_day_sessions


def _bars(rows: list[tuple[str, float, float, float, float, float]]) -> pd.DataFrame:
    """rows: (timestamp_iso, open, high, low, close, volume)."""
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp(r[0], tz="UTC") for r in rows],
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
        }
    )


def _synthetic_session(
    utc_open: str, utc_close: str, name: str = "synthetic", trading_date: dt.date = dt.date(2026, 1, 15)
) -> SessionWindow:
    """A hand-built SessionWindow, bypassing build_day_sessions, for tests
    that need full control over the window bounds (e.g. crossing UTC
    midnight) independent of the Asia/Europe/New York definitions."""
    open_ts = pd.Timestamp(utc_open, tz="UTC")
    close_ts = pd.Timestamp(utc_close, tz="UTC")
    return SessionWindow(
        name=name,
        trading_date=trading_date,
        tz_name="UTC",
        local_open=open_ts,
        local_close=close_ts,
        utc_open=open_ts,
        utc_close=close_ts,
        was_clipped=False,
        clip_reason=None,
    )


# Shared hand-computed fixture used by tests 1, 2, 6, 7:
#   open=100 (bar1, first) close=100 (bar4, last, same value by
#   coincidence but a different bar/time -- proves open/close come from
#   chronological position, not from being the min/max)
#   high=105 at 15:00, low=96 at 15:30, volume=50, vwap=101.133333...
_KNOWN_OHLC_ROWS = [
    ("2026-01-15 14:30", 100, 102, 99, 101, 10),
    ("2026-01-15 15:00", 101, 105, 100, 104, 20),
    ("2026-01-15 15:30", 104, 104, 96, 99, 15),
    ("2026-01-15 16:00", 99, 100, 97, 100, 5),
]
_KNOWN_SESSION = _synthetic_session("2026-01-15 14:30", "2026-01-15 16:30")


def test_synthetic_session_known_ohlc():
    geometry = compute_session_geometry(_bars(_KNOWN_OHLC_ROWS), _KNOWN_SESSION)
    assert geometry.open == 100
    assert geometry.high == 105
    assert geometry.low == 96
    assert geometry.close == 100
    assert geometry.volume == 50
    assert geometry.range == 9
    assert geometry.vwap == pytest.approx(101.13333333333334)
    assert geometry.bar_count == 4


def test_high_low_correctly_identified():
    geometry = compute_session_geometry(_bars(_KNOWN_OHLC_ROWS), _KNOWN_SESSION)
    assert geometry.high == 105
    assert geometry.low == 96


def test_open_is_first_chronological_bar():
    # Rows deliberately fed out of chronological order in the DataFrame --
    # open must reflect the earliest TIMESTAMP, not the first DataFrame row.
    shuffled = [
        _KNOWN_OHLC_ROWS[2],
        _KNOWN_OHLC_ROWS[0],
        _KNOWN_OHLC_ROWS[3],
        _KNOWN_OHLC_ROWS[1],
    ]
    geometry = compute_session_geometry(_bars(shuffled), _KNOWN_SESSION)
    assert geometry.open == 100  # bar1 (14:30), the true chronological first


def test_close_is_last_chronological_bar():
    shuffled = [
        _KNOWN_OHLC_ROWS[1],
        _KNOWN_OHLC_ROWS[3],
        _KNOWN_OHLC_ROWS[0],
        _KNOWN_OHLC_ROWS[2],
    ]
    geometry = compute_session_geometry(_bars(shuffled), _KNOWN_SESSION)
    assert geometry.close == 100  # bar4 (16:00), the true chronological last


def test_volume_summed_correctly():
    geometry = compute_session_geometry(_bars(_KNOWN_OHLC_ROWS), _KNOWN_SESSION)
    assert geometry.volume == 10 + 20 + 15 + 5


def test_vwap_calculated_correctly():
    geometry = compute_session_geometry(_bars(_KNOWN_OHLC_ROWS), _KNOWN_SESSION)
    expected_vwap = sum(((h + l + c) / 3) * v for _, o, h, l, c, v in _KNOWN_OHLC_ROWS) / 50
    assert geometry.vwap == pytest.approx(expected_vwap)


def test_high_low_timestamps_correct():
    geometry = compute_session_geometry(_bars(_KNOWN_OHLC_ROWS), _KNOWN_SESSION)
    assert geometry.high_time == pd.Timestamp("2026-01-15 15:00", tz="UTC")
    assert geometry.low_time == pd.Timestamp("2026-01-15 15:30", tz="UTC")


def test_zero_volume_bars_handled_explicitly():
    rows = [
        ("2026-01-15 14:30", 100, 101, 99, 100, 10),
        ("2026-01-15 15:00", 100, 103, 100, 102, 0),  # zero-volume, sets session high
        ("2026-01-15 15:30", 102, 102, 98, 101, 0),  # zero-volume, sets session low
        ("2026-01-15 16:00", 101, 101, 100, 100, 5),
    ]
    session = _synthetic_session("2026-01-15 14:30", "2026-01-15 16:30")
    geometry = compute_session_geometry(_bars(rows), session)

    assert geometry.zero_volume_bar_count == 2
    # Zero-volume bars' prices still count toward session high/low.
    assert geometry.high == 103
    assert geometry.low == 98
    # But contribute zero weight to VWAP -- only the two volume>0 bars matter.
    expected_vwap = (((101 + 99 + 100) / 3) * 10 + ((101 + 100 + 100) / 3) * 5) / 15
    assert geometry.vwap == pytest.approx(expected_vwap)


def test_missing_bars_dont_alter_session_boundaries():
    # Session nominally spans 14:30-16:30; only bars at 14:30 and 16:00 exist
    # (the 15:00 and 15:30 bars are simply absent -- a real gap).
    rows = [
        ("2026-01-15 14:30", 100, 101, 99, 100, 10),
        ("2026-01-15 16:00", 100, 102, 99, 101, 5),
    ]
    session = _synthetic_session("2026-01-15 14:30", "2026-01-15 16:30")
    geometry = compute_session_geometry(_bars(rows), session)

    # The window itself is untouched by which bars happen to exist.
    assert geometry.utc_open == pd.Timestamp("2026-01-15 14:30", tz="UTC")
    assert geometry.utc_close == pd.Timestamp("2026-01-15 16:30", tz="UTC")
    # Only the bars that actually exist are counted -- no fabrication.
    assert geometry.bar_count == 2
    assert geometry.open == 100
    assert geometry.close == 101


def test_session_crossing_utc_midnight():
    session = _synthetic_session(
        "2026-01-15 23:00", "2026-01-16 02:00", trading_date=dt.date(2026, 1, 16)
    )
    rows = [
        ("2026-01-15 23:00", 100, 101, 99, 100, 10),  # before midnight
        ("2026-01-15 23:30", 100, 104, 100, 103, 20),  # before midnight, session high
        ("2026-01-16 00:30", 103, 103, 95, 98, 15),  # after midnight, session low
        ("2026-01-16 01:30", 98, 99, 97, 99, 5),  # after midnight, last bar
    ]
    geometry = compute_session_geometry(_bars(rows), session)

    assert geometry.bar_count == 4
    assert geometry.open == 100  # 23:00 bar (before midnight)
    assert geometry.close == 99  # 01:30 bar (after midnight)
    assert geometry.high == 104
    assert geometry.low == 95
    assert geometry.high_time == pd.Timestamp("2026-01-15 23:30", tz="UTC")
    assert geometry.low_time == pd.Timestamp("2026-01-16 00:30", tz="UTC")


def test_dst_transition_session_via_calendar_layer():
    # 2026-03-09: the first US trading day after US DST spring-forward.
    # New York session UTC bounds come from the REAL calendar layer
    # (sessions.py + exchange.py), not hand-constructed here.
    calendar = CMEEquityCalendar()
    day_sessions = build_day_sessions(dt.date(2026, 3, 9), calendar)
    ny_session = day_sessions["new_york"]
    assert ny_session.utc_open == pd.Timestamp("2026-03-09 13:30", tz="UTC")  # sanity check

    rows = [
        ("2026-03-09 13:30", 100, 101, 99, 100, 10),
        ("2026-03-09 15:00", 100, 106, 100, 105, 25),
        ("2026-03-09 19:59", 105, 105, 101, 102, 8),
    ]
    geometry = compute_session_geometry(_bars(rows), ny_session)

    assert geometry.bar_count == 3
    assert geometry.open == 100
    assert geometry.close == 102
    assert geometry.high == 106
    assert geometry.utc_open == ny_session.utc_open
    assert geometry.utc_close == ny_session.utc_close


def test_early_close_session_terminates_correctly():
    # 2025-11-27 (Thanksgiving): New York session is clipped to CME's
    # actual early close (18:00 UTC), not the nominal 21:00 UTC.
    calendar = CMEEquityCalendar()
    day_sessions = build_day_sessions(dt.date(2025, 11, 27), calendar)
    ny_session = day_sessions["new_york"]
    assert ny_session.was_clipped is True
    assert ny_session.utc_close == pd.Timestamp("2025-11-27 18:00", tz="UTC")  # sanity check

    rows = [
        ("2025-11-27 14:30", 100, 101, 99, 100, 10),
        ("2025-11-27 17:00", 100, 103, 100, 102, 20),
        # This bar is timestamped AFTER the clipped close -- must be excluded,
        # even though it would fall inside the nominal (unclipped) 09:30-16:00 ET window.
        ("2025-11-27 18:30", 102, 999, 1, 999, 50),
    ]
    geometry = compute_session_geometry(_bars(rows), ny_session)

    assert geometry.bar_count == 2
    assert geometry.close == 102  # the 17:00 bar, not the excluded 18:30 one
    assert geometry.high == 103  # not 999 -- the excluded bar must not leak in
    assert geometry.low == 99


def test_empty_session_raises_explicitly():
    # All bars fall outside the session window entirely.
    rows = [
        ("2026-01-15 10:00", 100, 101, 99, 100, 10),
        ("2026-01-15 20:00", 100, 101, 99, 100, 10),
    ]
    session = _synthetic_session("2026-01-15 14:30", "2026-01-15 16:30")
    with pytest.raises(EmptySessionError):
        compute_session_geometry(_bars(rows), session)


def test_duplicate_bars_do_not_silently_double_count():
    rows = [
        ("2026-01-15 14:30", 100, 101, 99, 100, 10),
        ("2026-01-15 15:00", 100, 102, 100, 101, 20),
        # Duplicate timestamp with DIFFERENT values -- if silently summed,
        # volume would wrongly read 55 instead of raising.
        ("2026-01-15 15:00", 101, 110, 101, 105, 25),
    ]
    session = _synthetic_session("2026-01-15 14:30", "2026-01-15 16:30")
    with pytest.raises(DuplicateBarsError):
        compute_session_geometry(_bars(rows), session)
