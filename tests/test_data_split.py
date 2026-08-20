"""Tests for src.research.data_split -- the locked out-of-sample boundaries.

The one thing that must never regress silently: locked_test_slice refusing
access without an explicit confirmed_by name.
"""

import datetime as dt

import pandas as pd
import pytest

from src.research.data_split import (
    DISCOVERY_END,
    DISCOVERY_START,
    LOCKED_TEST_END,
    LOCKED_TEST_START,
    VALIDATION_END,
    VALIDATION_START,
    LockedTestAccessError,
    discovery_slice,
    locked_test_slice,
    validation_slice,
)


def _all_dates_df() -> pd.DataFrame:
    dates = pd.date_range(DISCOVERY_START, LOCKED_TEST_END, freq="7D").date
    return pd.DataFrame({"trading_date": dates, "value": range(len(dates))})


def test_discovery_slice_excludes_validation_and_locked_dates():
    df = _all_dates_df()
    result = discovery_slice(df)
    assert (result["trading_date"] <= DISCOVERY_END).all()
    assert (result["trading_date"] >= DISCOVERY_START).all()


def test_validation_slice_bounds():
    df = _all_dates_df()
    result = validation_slice(df)
    assert (result["trading_date"] >= VALIDATION_START).all()
    assert (result["trading_date"] <= VALIDATION_END).all()


def test_locked_test_slice_raises_without_confirmation():
    df = _all_dates_df()
    with pytest.raises(LockedTestAccessError):
        locked_test_slice(df, confirmed_by="")
    with pytest.raises(LockedTestAccessError):
        locked_test_slice(df, confirmed_by=None)  # type: ignore[arg-type]


def test_locked_test_slice_raises_when_called_without_confirmed_by_at_all():
    df = _all_dates_df()
    with pytest.raises(TypeError):
        locked_test_slice(df)  # confirmed_by is keyword-only, no default


def test_locked_test_slice_works_with_explicit_name():
    df = _all_dates_df()
    result = locked_test_slice(df, confirmed_by="Hussan")
    assert (result["trading_date"] >= LOCKED_TEST_START).all()
    assert (result["trading_date"] <= LOCKED_TEST_END).all()


def test_three_buckets_partition_the_full_range_without_overlap():
    df = _all_dates_df()
    d = discovery_slice(df)
    v = validation_slice(df)
    locked = locked_test_slice(df, confirmed_by="Hussan")
    assert set(d["trading_date"]) & set(v["trading_date"]) == set()
    assert set(v["trading_date"]) & set(locked["trading_date"]) == set()
    assert set(d["trading_date"]) & set(locked["trading_date"]) == set()
