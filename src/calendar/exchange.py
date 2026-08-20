"""CME Globex trading-calendar wrapper for CME equity index futures (ES, NQ, RTY, ...).

This module answers exactly one question, authoritatively: for a given
calendar date, is the CME equity-index Globex market open, closed for a
full holiday, or open on an abbreviated (early-close) schedule -- and if
open, what are its exact UTC open/close bounds?

Source of truth: ``pandas_market_calendars``'s ``CME_Equity`` calendar.
That calendar does NOT mirror the NYSE calendar -- several NYSE holidays
(MLK Day, Presidents Day, Memorial Day, Labor Day, Juneteenth, the day
before/after Independence Day, Thanksgiving, the day after Thanksgiving,
Christmas Eve) are early-close days for CME equity futures rather than
full closures, because Globex keeps trading nearly continuously even
when the underlying cash equity market is shut. Only New Year's Day,
Good Friday, and Christmas Day are full CME equity-futures closures.
This distinction matters for R001: an "Asia" or "Europe" session block
on a NYSE holiday is still real, tradeable ES data.

Every timestamp this module returns is UTC. Local-time interpretation
(for session construction) is layered on top in ``sessions.py`` -- this
module deliberately stays timezone-agnostic about anything other than
"is Globex open, and when".

KNOWN GAPS -- see docs/known_gaps.md for full detail, rationale, and
revisit triggers. Summary:

  * ``CME_Equity`` (what this module wraps) misses at least one ad hoc
    CME special closure not covered by its recurring holiday rules --
    confirmed on 2025-01-09 (National Day of Mourning for President
    Carter), where real trading occurred with an early close but this
    calendar reports the whole day as a full holiday. Deferred; pinned
    by ``tests/test_known_gaps.py``.
  * We deliberately use ``CME_Equity``, not the library's other CME
    equity-index calendar ``CME Globex Equity`` -- the latter gets the
    real 2005-09 to 2012-11 shortened-hours regime wrong and doesn't
    model the daily maintenance break at all.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

UTC = ZoneInfo("UTC")

# CME equity index futures' standard (non-holiday) day-session close is
# 16:00 America/Chicago. Any trading day whose actual close differs from
# this is, by definition, an early-close day (Thanksgiving, day after
# Thanksgiving, Christmas Eve, MLK Day, Presidents Day, Memorial Day,
# Labor Day, Juneteenth, day before/after Independence Day, Good Friday
# in the small number of years CME ran an abbreviated Good Friday
# session instead of a full closure). We detect early closes this way,
# rather than hardcoding the holiday list ourselves, so this module
# stays correct as CME's own schedule evolves and as
# pandas_market_calendars updates its holiday rules.
_STANDARD_CLOSE_LOCAL = dt.time(16, 0)
_CHICAGO = ZoneInfo("America/Chicago")


@dataclass(frozen=True)
class GlobexTradingDay:
    """The CME Globex trading session for one CME trading date.

    ``trading_date`` is the CME "trade date" convention: the session
    that opens Sunday/weekday evening and closes the following
    afternoon is attributed to the date of its afternoon close, not the
    date it opened on. E.g. the session that opens Sunday 5pm CT and
    closes Monday 4pm CT is trading_date == that Monday.
    """

    trading_date: dt.date
    open_utc: pd.Timestamp
    close_utc: pd.Timestamp
    is_early_close: bool
    break_start_utc: pd.Timestamp | None
    break_end_utc: pd.Timestamp | None
    """Daily maintenance-break bounds, if any. On some early-close days
    pandas_market_calendars represents "no real break" degenerately as
    break_start == break_end == market_close -- passed through as-is
    rather than special-cased, since callers (see src/ingest/validate.py)
    treat a zero-width break as simply contributing nothing to exclude."""


class CMEEquityCalendar:
    """Thin, explicit wrapper around pandas_market_calendars' CME_Equity calendar.

    Kept deliberately small: this class answers calendar questions
    (trading day? holiday? early close? exact open/close?) and nothing
    else. Session-boundary construction (Asia/Europe/New York) lives in
    ``sessions.py`` and consumes this class's output rather than talking
    to pandas_market_calendars directly, so there is exactly one place
    in the codebase that knows how to interpret the CME schedule.
    """

    def __init__(self) -> None:
        self._calendar = mcal.get_calendar("CME_Equity")
        # Memoizes date -> GlobexTradingDay | None. `is_trading_day` and
        # `trading_day_bounds` both resolve through this cache -- see
        # `warm_cache` for the bulk-populate path used before validating
        # large real datasets (each individual pandas_market_calendars query
        # has real per-call overhead; at millions of per-row calendar
        # lookups that overhead dominates runtime, so a range is looked up
        # in one batched call and diffed against a cold single-date query
        # only for whatever wasn't pre-warmed).
        self._bounds_cache: dict[dt.date, GlobexTradingDay | None] = {}

    def warm_cache(self, start: dt.date, end: dt.date) -> None:
        """Pre-populate the bounds cache for every date in [start, end] using
        two batched pandas_market_calendars queries, instead of one query
        per date. Pure performance optimization -- `is_trading_day` and
        `trading_day_bounds` return identical results whether or not the
        cache has been warmed for a given date; this just makes repeated
        lookups over a wide range fast."""
        valid_dates = {ts.date() for ts in self._calendar.valid_days(start_date=start, end_date=end)}
        schedule = self._calendar.schedule(start_date=start, end_date=end, tz="UTC")
        schedule_by_date = {
            (idx.date() if hasattr(idx, "date") else idx): row for idx, row in schedule.iterrows()
        }

        date = start
        while date <= end:
            if date in valid_dates:
                self._bounds_cache[date] = self._build_trading_day(date, schedule_by_date[date])
            else:
                self._bounds_cache[date] = None
            date += dt.timedelta(days=1)

    @staticmethod
    def _build_trading_day(date: dt.date, row: pd.Series) -> GlobexTradingDay:
        open_utc = row["market_open"]
        close_utc = row["market_close"]
        break_start_utc = row.get("break_start")
        break_end_utc = row.get("break_end")

        close_local_time = close_utc.tz_convert(_CHICAGO).time()
        is_early_close = close_local_time != _STANDARD_CLOSE_LOCAL

        return GlobexTradingDay(
            trading_date=date,
            open_utc=open_utc,
            close_utc=close_utc,
            is_early_close=is_early_close,
            break_start_utc=break_start_utc if pd.notna(break_start_utc) else None,
            break_end_utc=break_end_utc if pd.notna(break_end_utc) else None,
        )

    def _get_bounds(self, date: dt.date) -> GlobexTradingDay | None:
        if date in self._bounds_cache:
            return self._bounds_cache[date]

        valid = self._calendar.valid_days(start_date=date, end_date=date)
        if len(valid) == 0:
            self._bounds_cache[date] = None
            return None

        schedule = self._calendar.schedule(start_date=date, end_date=date, tz="UTC")
        day = self._build_trading_day(date, schedule.iloc[0])
        self._bounds_cache[date] = day
        return day

    def is_trading_day(self, date: dt.date) -> bool:
        """True if CME equity Globex trades at all on this date.

        False for full-closure holidays (New Year's Day, Good Friday,
        Christmas Day) and for weekends outside the Sun-evening-open /
        Fri-afternoon-close week. Early-close days (Thanksgiving, etc.)
        are still trading days and return True.
        """
        return self._get_bounds(date) is not None

    def trading_days(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """All CME trading dates in [start, end], inclusive."""
        valid = self._calendar.valid_days(start_date=start, end_date=end)
        return [ts.date() for ts in valid]

    def holidays(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """Full-closure holidays in [start, end] (weekends excluded).

        These are dates where CME equity Globex does not trade at all --
        not early-close days, which ``is_trading_day`` still counts as
        trading days.
        """
        all_days = {
            (start + dt.timedelta(days=n)).isoformat()
            for n in range((end - start).days + 1)
        }
        trading = {d.isoformat() for d in self.trading_days(start, end)}
        non_trading = sorted(all_days - trading)
        return [
            dt.date.fromisoformat(d)
            for d in non_trading
            if dt.date.fromisoformat(d).weekday() < 5  # exclude plain Sat/Sun
        ]

    def trading_day_bounds(self, date: dt.date) -> GlobexTradingDay | None:
        """Exact UTC open/close for a CME trading date, or None if it's a full holiday.

        ``is_early_close`` is True whenever the actual close deviates
        from the standard 16:00 America/Chicago close -- see module
        docstring for why we detect it this way instead of hardcoding a
        holiday list.
        """
        return self._get_bounds(date)
