"""Locked out-of-sample split (blueprint Phase 65), confirmed 2026-08-15.

Three buckets over the real labeled dataset (src/research's session_labels
output, 3,614 distinct trading dates):

    DISCOVERY   2010-06-07 -> 2021-12-31  (2,421 trading dates)
    VALIDATION  2022-01-03 -> 2023-12-29  (  516 trading dates)
    LOCKED_TEST 2024-01-02 -> 2026-08-14  (  677 trading dates)

See docs/data_split.md for the full rationale and confirmation record.

H001-H012 (blueprint Phase 54) run on DISCOVERY only. VALIDATION exists for
iterating on hypothesis definitions without contaminating the final test.
LOCKED_TEST must not be read by any hypothesis-testing code until the user
explicitly confirms, by name, that discovery/validation work is finalized
-- see `locked_test_slice` below. Accidentally reading it before that is a
bug, not a convenience; that's why it raises rather than silently working
with a default.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

DISCOVERY_START = dt.date(2010, 6, 7)
DISCOVERY_END = dt.date(2021, 12, 31)
VALIDATION_START = dt.date(2022, 1, 3)
VALIDATION_END = dt.date(2023, 12, 29)
LOCKED_TEST_START = dt.date(2024, 1, 2)
LOCKED_TEST_END = dt.date(2026, 8, 14)


class LockedTestAccessError(RuntimeError):
    """Raised when locked-test data is read without explicit named confirmation."""


def _as_date(x) -> dt.date:
    if isinstance(x, dt.date) and not isinstance(x, dt.datetime):
        return x
    return pd.Timestamp(x).date()


def discovery_slice(df: pd.DataFrame, date_col: str = "trading_date") -> pd.DataFrame:
    dates = df[date_col].map(_as_date)
    return df[(dates >= DISCOVERY_START) & (dates <= DISCOVERY_END)]


def validation_slice(df: pd.DataFrame, date_col: str = "trading_date") -> pd.DataFrame:
    dates = df[date_col].map(_as_date)
    return df[(dates >= VALIDATION_START) & (dates <= VALIDATION_END)]


def locked_test_slice(df: pd.DataFrame, *, confirmed_by: str, date_col: str = "trading_date") -> pd.DataFrame:
    """Only path to the locked-test range. `confirmed_by` must be a real
    name, passed explicitly and deliberately by the caller -- there is no
    default that makes this "just work". If you're hitting this error, stop
    and get the user's explicit go-ahead first; do not work around it.
    """
    if not confirmed_by or not isinstance(confirmed_by, str) or not confirmed_by.strip():
        raise LockedTestAccessError(
            "Locked-test range access requires explicit confirmation by name "
            "(pass confirmed_by='<name>'). This is deliberate -- see "
            "docs/data_split.md. Do not add a default value to bypass this."
        )
    dates = df[date_col].map(_as_date)
    return df[(dates >= LOCKED_TEST_START) & (dates <= LOCKED_TEST_END)]
