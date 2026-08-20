"""Tests for src.ingest.validate.

All bar data is synthetic and clearly labeled as such -- these tests
prove the validation CHECKS are implemented correctly, not that any
real ES data is clean. See validate.py's module docstring: running
these checks against synthetic data and treating the result as a
statement about real market data would defeat Phase 47's purpose.
"""

import datetime as dt

import pandas as pd
import pytest

from src.calendar.contracts import build_contract
from src.calendar.exchange import CMEEquityCalendar
from src.ingest.validate import (
    check_bars_after_contract_expiration,
    check_bars_outside_globex_hours,
    check_duplicate_timestamps,
    check_impossible_prices,
    check_missing_bars,
    check_zero_volume,
    run_full_validation,
)


@pytest.fixture(scope="module")
def calendar() -> CMEEquityCalendar:
    return CMEEquityCalendar()


def _canonical_bars(rows: list[tuple]) -> pd.DataFrame:
    """rows: (timestamp_iso, open, high, low, close, volume, contract_symbol)."""
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp(r[0], tz="UTC") for r in rows],
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
            "contract_symbol": [r[6] for r in rows],
        }
    )


def test_check_duplicate_timestamps_flags_repeated_bar():
    rows = [
        ("2026-01-15 14:30", 100, 101, 99, 100, 10, "ESH26"),
        ("2026-01-15 14:30", 100, 105, 99, 104, 999, "ESH26"),  # duplicate timestamp+symbol
        ("2026-01-15 14:31", 100, 101, 99, 100, 10, "ESH26"),
    ]
    issues = check_duplicate_timestamps(_canonical_bars(rows))
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].count == 1  # one distinct duplicated pair


def test_check_duplicate_timestamps_clean_data_has_no_issues():
    rows = [
        ("2026-01-15 14:30", 100, 101, 99, 100, 10, "ESH26"),
        ("2026-01-15 14:31", 100, 101, 99, 100, 10, "ESH26"),
    ]
    assert check_duplicate_timestamps(_canonical_bars(rows)) == []


def test_check_impossible_prices_flags_high_below_low():
    rows = [("2026-01-15 14:30", 100, 98, 99, 100, 10, "ESH26")]  # high < low
    issues = check_impossible_prices(_canonical_bars(rows))
    assert len(issues) == 1
    assert issues[0].count == 1


def test_check_impossible_prices_flags_nonpositive_price():
    rows = [("2026-01-15 14:30", -5, 101, 99, 100, 10, "ESH26")]
    issues = check_impossible_prices(_canonical_bars(rows))
    assert len(issues) == 1


def test_check_impossible_prices_clean_data_has_no_issues():
    rows = [("2026-01-15 14:30", 100, 101, 99, 100, 10, "ESH26")]
    assert check_impossible_prices(_canonical_bars(rows)) == []


def test_check_zero_volume_is_a_warning_not_an_error():
    rows = [("2026-01-15 14:30", 100, 101, 99, 100, 0, "ESH26")]
    issues = check_zero_volume(_canonical_bars(rows))
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].count == 1


def test_check_bars_outside_globex_hours_flags_holiday_bar(calendar):
    rows = [("2025-12-25 18:00", 100, 101, 99, 100, 10, "ESZ25")]  # Christmas, full holiday
    issues = check_bars_outside_globex_hours(_canonical_bars(rows), calendar)
    assert len(issues) == 1
    assert issues[0].severity == "error"


def test_check_bars_outside_globex_hours_clean_data_has_no_issues(calendar):
    rows = [("2026-01-15 14:30", 100, 101, 99, 100, 10, "ESH26")]  # ordinary trading time
    assert check_bars_outside_globex_hours(_canonical_bars(rows), calendar) == []


def test_check_bars_after_contract_expiration_flags_stale_symbol(calendar):
    esh26 = build_contract(2026, 3, calendar)  # last trade terminates 2026-03-20 13:30 UTC
    rows = [
        ("2026-03-20 12:00", 100, 101, 99, 100, 10, "ESH26"),  # before termination: fine
        ("2026-03-20 14:00", 100, 101, 99, 100, 10, "ESH26"),  # after termination: roll error
    ]
    issues = check_bars_after_contract_expiration(_canonical_bars(rows), {"ESH26": esh26})
    assert len(issues) == 1
    assert issues[0].count == 1


def test_check_missing_bars_detects_one_removed_bar_from_hourly_grid(calendar):
    # Full expected hourly grid for CME trading date 2026-01-15 (confirmed
    # via calendar.trading_day_bounds): 24 timestamps, open 2026-01-14 23:00
    # UTC through close 2026-01-15 22:00 UTC, correctly excluding the daily
    # 21:15-21:30 UTC maintenance break. We omit "05:00" to simulate one
    # genuinely missing bar.
    full_grid = list(
        pd.date_range("2026-01-14 23:00", "2026-01-15 21:15", freq="1h", tz="UTC", inclusive="left")
    ) + list(
        pd.date_range("2026-01-15 21:30", "2026-01-15 22:00", freq="1h", tz="UTC", inclusive="left")
    )
    missing_ts = pd.Timestamp("2026-01-15 05:00", tz="UTC")
    present = [ts for ts in full_grid if ts != missing_ts]

    rows = [(ts.isoformat(), 100, 101, 99, 100, 10, "ESH26") for ts in present]
    issues = check_missing_bars(_canonical_bars(rows), calendar, pd.Timedelta("1h"))

    assert len(issues) == 1
    assert issues[0].count == 1
    assert issues[0].sample[0] == ("ESH26", missing_ts)


def test_check_missing_bars_does_not_flag_the_maintenance_break_as_missing(calendar):
    # Same full grid, no bars omitted at all -- the break itself (21:15-21:30
    # UTC) must NOT appear as a false-positive gap.
    full_grid = list(
        pd.date_range("2026-01-14 23:00", "2026-01-15 21:15", freq="1h", tz="UTC", inclusive="left")
    ) + list(
        pd.date_range("2026-01-15 21:30", "2026-01-15 22:00", freq="1h", tz="UTC", inclusive="left")
    )
    rows = [(ts.isoformat(), 100, 101, 99, 100, 10, "ESH26") for ts in full_grid]
    issues = check_missing_bars(_canonical_bars(rows), calendar, pd.Timedelta("1h"))
    assert issues == []


def test_run_full_validation_aggregates_and_flags_errors(calendar):
    rows = [
        ("2026-01-15 14:30", 100, 98, 99, 100, 10, "ESH26"),  # impossible price -> error
        ("2026-01-15 14:31", 100, 101, 99, 100, 0, "ESH26"),  # zero volume -> warning
    ]
    report = run_full_validation(_canonical_bars(rows), calendar)
    assert report.has_errors is True
    checks_seen = {issue.check for issue in report.issues}
    assert "impossible_prices" in checks_seen
    assert "zero_volume" in checks_seen


def test_run_full_validation_clean_data_has_no_errors(calendar):
    rows = [
        ("2026-01-15 14:30", 100, 101, 99, 100, 10, "ESH26"),
        ("2026-01-15 14:31", 100, 102, 99, 101, 12, "ESH26"),
    ]
    report = run_full_validation(_canonical_bars(rows), calendar)
    assert report.has_errors is False
