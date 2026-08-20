"""ES bar data validation (blueprint Phase 47).

"Before analysis, check missing bars, duplicates, bad timestamps,
impossible prices, zero volume, roll errors, holiday errors, DST
errors."

Operates on canonical-schema bar DataFrames (see bars.py:
CANONICAL_COLUMNS). No real ES data has been ingested yet -- these
checks are built and unit-tested against clearly-labeled synthetic
fixtures now (tests/test_validate.py) so they're ready the moment real
data arrives. Running this module's checks against synthetic data and
reporting the result as if it validated anything about real market
behavior would defeat the entire point of Phase 47 -- these checks
validate DATA QUALITY, and synthetic fixtures only prove the CHECKS
themselves are implemented correctly.

DST errors are covered implicitly, not by a dedicated check: because
every canonical timestamp is normalized to UTC by
`calendar.timestamps.to_utc_timestamp` before it ever reaches this
module (see bars.py), a raw local timestamp that fell in a
nonexistent/ambiguous DST wall-clock hour would already have failed (or
been forced to pick a UTC offset) at normalization time, upstream of
here. `check_bars_outside_globex_hours` below is the backstop: a
timestamp that ends up in the wrong place because of a DST handling bug
upstream will, in the overwhelming majority of cases, land outside every
known Globex session window and get caught there.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.calendar.contracts import FuturesContract
from src.calendar.exchange import CMEEquityCalendar
from src.calendar.timestamps import NoTradingDayFoundError, trading_date_for_timestamp

_SAMPLE_LIMIT = 10


@dataclass(frozen=True)
class ValidationIssue:
    check: str
    severity: str  # "error" | "warning"
    message: str
    count: int
    sample: list = field(default_factory=list)


@dataclass(frozen=True)
class ValidationReport:
    issues: list[ValidationIssue]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def check_duplicate_timestamps(df: pd.DataFrame) -> list[ValidationIssue]:
    """Duplicate (contract_symbol, timestamp) pairs -- same bar reported twice."""
    dup_mask = df.duplicated(subset=["contract_symbol", "timestamp"], keep=False)
    if not dup_mask.any():
        return []
    dupes = df.loc[dup_mask, ["contract_symbol", "timestamp"]].drop_duplicates()
    sample = list(dupes.itertuples(index=False, name=None))[:_SAMPLE_LIMIT]
    return [
        ValidationIssue(
            check="duplicate_timestamps",
            severity="error",
            message=f"{len(dupes)} duplicate (contract_symbol, timestamp) pair(s) found",
            count=len(dupes),
            sample=sample,
        )
    ]


def check_impossible_prices(df: pd.DataFrame) -> list[ValidationIssue]:
    """high < low, high/low inconsistent with open/close, or non-positive prices."""
    bad = (
        (df["high"] < df["low"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
        | (df["open"] <= 0)
        | (df["high"] <= 0)
        | (df["low"] <= 0)
        | (df["close"] <= 0)
    )
    if not bad.any():
        return []
    bad_rows = df.loc[bad, ["contract_symbol", "timestamp"]]
    sample = list(bad_rows.itertuples(index=False, name=None))[:_SAMPLE_LIMIT]
    return [
        ValidationIssue(
            check="impossible_prices",
            severity="error",
            message=f"{int(bad.sum())} bar(s) with internally inconsistent OHLC prices",
            count=int(bad.sum()),
            sample=sample,
        )
    ]


def check_zero_volume(df: pd.DataFrame) -> list[ValidationIssue]:
    """Zero-volume bars -- not necessarily wrong (illiquid overnight windows
    are real), but always worth surfacing rather than silently ignoring."""
    zero = df["volume"] == 0
    if not zero.any():
        return []
    sample_rows = df.loc[zero, ["contract_symbol", "timestamp"]]
    sample = list(sample_rows.itertuples(index=False, name=None))[:_SAMPLE_LIMIT]
    return [
        ValidationIssue(
            check="zero_volume",
            severity="warning",
            message=f"{int(zero.sum())} zero-volume bar(s)",
            count=int(zero.sum()),
            sample=sample,
        )
    ]


def check_bars_outside_globex_hours(
    df: pd.DataFrame, calendar: CMEEquityCalendar
) -> list[ValidationIssue]:
    """Bars timestamped outside any real CME Globex trading session --
    covers both "holiday errors" (a bar exists on a full-closure date)
    and "bad timestamps" (garbage/misparsed timestamps) from Phase 47's
    checklist, since both surface the same way: no trading session
    contains the timestamp."""
    unique_ts = df["timestamp"].drop_duplicates()
    bad_ts = set()
    for ts in unique_ts:
        try:
            trading_date_for_timestamp(ts, calendar)
        except NoTradingDayFoundError:
            bad_ts.add(ts)

    if not bad_ts:
        return []
    bad_rows = df.loc[df["timestamp"].isin(bad_ts), ["contract_symbol", "timestamp"]]
    sample = list(bad_rows.itertuples(index=False, name=None))[:_SAMPLE_LIMIT]
    return [
        ValidationIssue(
            check="bars_outside_globex_hours",
            severity="error",
            message=(
                f"{len(bad_rows)} bar(s) with timestamps outside any CME Globex "
                "trading session (holiday, or bad/corrupt timestamp)"
            ),
            count=len(bad_rows),
            sample=sample,
        )
    ]


def check_bars_after_contract_expiration(
    df: pd.DataFrame, contracts: dict[str, FuturesContract]
) -> list[ValidationIssue]:
    """"Roll errors": bars tagged with a contract_symbol timestamped at or
    after that contract's own last-trade termination time. Signals a
    continuous series that wasn't rolled forward -- data tagged with a
    stale/expired symbol."""
    bad_mask = pd.Series(False, index=df.index)
    for symbol, contract in contracts.items():
        symbol_rows = df["contract_symbol"] == symbol
        bad_mask |= symbol_rows & (df["timestamp"] >= contract.last_trade_terminates_utc)

    if not bad_mask.any():
        return []
    bad_rows = df.loc[bad_mask, ["contract_symbol", "timestamp"]]
    sample = list(bad_rows.itertuples(index=False, name=None))[:_SAMPLE_LIMIT]
    return [
        ValidationIssue(
            check="bars_after_contract_expiration",
            severity="error",
            message=(
                f"{len(bad_rows)} bar(s) timestamped after their contract's own "
                "last-trade termination time -- possible unrolled/stale contract tag"
            ),
            count=len(bad_rows),
            sample=sample,
        )
    ]


def check_missing_bars(
    df: pd.DataFrame, calendar: CMEEquityCalendar, expected_interval: pd.Timedelta
) -> list[ValidationIssue]:
    """Gaps in the expected regular bar grid, per contract, within each
    trading date actually present in the data -- correctly excluding the
    daily maintenance break (not a gap, it's real non-trading time) by
    building the expected grid from the calendar's own open/break/close
    bounds rather than assuming continuous coverage.

    Only checks trading dates that have at least one bar present for
    that symbol; a trading date with zero bars for a symbol is a
    different failure mode (total absence, not a gap) and isn't reported
    here to keep this check's meaning unambiguous.
    """
    issues: list[ValidationIssue] = []

    for symbol, group in df.groupby("contract_symbol"):
        actual_ts = set(group["timestamp"])
        trading_dates = set()
        for ts in actual_ts:
            try:
                trading_dates.add(trading_date_for_timestamp(ts, calendar))
            except NoTradingDayFoundError:
                continue  # already reported by check_bars_outside_globex_hours

        missing: list[tuple[str, pd.Timestamp]] = []
        for trading_date in trading_dates:
            day = calendar.trading_day_bounds(trading_date)
            if day is None:
                continue

            segments: list[tuple[pd.Timestamp, pd.Timestamp]] = []
            if day.break_start_utc is not None and day.break_end_utc is not None and (
                day.break_start_utc < day.break_end_utc
            ):
                segments.append((day.open_utc, day.break_start_utc))
                segments.append((day.break_end_utc, day.close_utc))
            else:
                segments.append((day.open_utc, day.close_utc))

            for seg_start, seg_end in segments:
                expected = pd.date_range(
                    start=seg_start, end=seg_end, freq=expected_interval, inclusive="left"
                )
                for expected_ts in expected:
                    if expected_ts not in actual_ts:
                        missing.append((symbol, expected_ts))

        if missing:
            issues.append(
                ValidationIssue(
                    check="missing_bars",
                    severity="warning",
                    message=(
                        f"{len(missing)} expected bar(s) missing for {symbol} "
                        f"at {expected_interval} resolution"
                    ),
                    count=len(missing),
                    sample=missing[:_SAMPLE_LIMIT],
                )
            )

    return issues


def run_full_validation(
    df: pd.DataFrame,
    calendar: CMEEquityCalendar,
    contracts: dict[str, FuturesContract] | None = None,
    expected_interval: pd.Timedelta | None = None,
) -> ValidationReport:
    """Run every applicable check. `contracts` and `expected_interval` are
    optional -- the roll-error and missing-bar checks are skipped
    (silently, since they're opt-in extras, not part of the core schema)
    if not supplied."""
    issues: list[ValidationIssue] = []
    issues += check_duplicate_timestamps(df)
    issues += check_impossible_prices(df)
    issues += check_zero_volume(df)
    issues += check_bars_outside_globex_hours(df, calendar)
    if contracts is not None:
        issues += check_bars_after_contract_expiration(df, contracts)
    if expected_interval is not None:
        issues += check_missing_bars(df, calendar, expected_interval)
    return ValidationReport(issues=issues)
