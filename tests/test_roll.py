"""Tests for src.calendar.roll.volume_crossover_roll_date.

Uses synthetic volume series (not real ES data -- none has been
ingested yet, see roll.py's module docstring) purely to verify the
crossover-detection algorithm itself is correct.
"""

import datetime as dt

import pandas as pd

from src.calendar.roll import (
    majority_crossover_roll_date,
    resolve_roll_date,
    volume_crossover_roll_date,
)


def _dates(start: dt.date, n: int) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range(n)]


def test_detects_simple_crossover():
    idx = _dates(dt.date(2026, 3, 1), 5)
    front = pd.Series([100, 90, 80, 40, 30], index=idx)
    next_ = pd.Series([10, 20, 30, 50, 60], index=idx)

    decision = volume_crossover_roll_date(front, next_, confirm_days=1)

    assert decision is not None
    assert decision.roll_date == dt.date(2026, 3, 4)


def test_requires_sustained_crossover_when_confirm_days_greater_than_one():
    idx = _dates(dt.date(2026, 3, 1), 6)
    # Day 3 (index 2) is a single noisy spike where next > front, then
    # front reclaims the lead before finally, genuinely, crossing on day 5.
    front = pd.Series([100, 90, 40, 85, 30, 20], index=idx)
    next_ = pd.Series([10, 20, 60, 25, 50, 60], index=idx)

    single_day = volume_crossover_roll_date(front, next_, confirm_days=1)
    assert single_day is not None
    assert single_day.roll_date == dt.date(2026, 3, 3)  # the noisy spike

    sustained = volume_crossover_roll_date(front, next_, confirm_days=2)
    assert sustained is not None
    assert sustained.roll_date == dt.date(2026, 3, 5)  # the real, sustained crossover


def test_returns_none_when_crossover_never_happens():
    idx = _dates(dt.date(2026, 3, 1), 5)
    front = pd.Series([100, 100, 100, 100, 100], index=idx)
    next_ = pd.Series([10, 10, 10, 10, 10], index=idx)

    assert volume_crossover_roll_date(front, next_) is None


def test_only_overlapping_dates_are_considered():
    front = pd.Series([100, 90], index=_dates(dt.date(2026, 3, 1), 2))
    next_ = pd.Series([50], index=_dates(dt.date(2026, 3, 1), 1))  # no overlap on day 2

    # Only one overlapping day, and front > next on it -- no crossover.
    assert volume_crossover_roll_date(front, next_) is None


def test_majority_fallback_resolves_an_interrupted_streak():
    # Mirrors the real ESZ10->ESH11 pattern: next wins two days, front
    # reclaims one day (near-tie), then next wins four more in a row --
    # the longest unbroken streak (4) falls one short of confirm_days=5,
    # but 6 of 8 days in the window favor next -- a clear majority.
    idx = _dates(dt.date(2026, 3, 1), 8)
    front = pd.Series([10, 10, 11, 20, 5, 5, 5, 12], index=idx)
    next_ = pd.Series([15, 20, 10, 30, 40, 35, 45, 8], index=idx)

    strict = volume_crossover_roll_date(front, next_, confirm_days=5)
    assert strict is None  # no 5-in-a-row streak exists

    fallback = majority_crossover_roll_date(front, next_, window_days=8)
    assert fallback is not None
    assert fallback.roll_date == dt.date(2026, 3, 1)  # 6/8 days in this window favor next


def test_resolve_roll_date_prefers_strict_result_when_available():
    idx = _dates(dt.date(2026, 3, 1), 5)
    front = pd.Series([100, 90, 80, 40, 30], index=idx)
    next_ = pd.Series([10, 20, 30, 50, 60], index=idx)

    strict = volume_crossover_roll_date(front, next_, confirm_days=1)
    resolved = resolve_roll_date(front, next_, confirm_days=1)
    assert resolved == strict


def test_resolve_roll_date_falls_back_when_strict_rule_finds_nothing():
    idx = _dates(dt.date(2026, 3, 1), 8)
    front = pd.Series([10, 10, 11, 20, 5, 5, 5, 12], index=idx)
    next_ = pd.Series([15, 20, 10, 30, 40, 35, 45, 8], index=idx)

    assert volume_crossover_roll_date(front, next_, confirm_days=5) is None
    resolved = resolve_roll_date(front, next_, confirm_days=5, fallback_window_days=8)
    assert resolved is not None
    assert resolved.roll_date == dt.date(2026, 3, 1)
