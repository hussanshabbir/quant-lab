"""Canonical bar-timestamp normalization (blueprint Phase 49, timestamp half).

Raw incoming bar data can arrive with timestamps in almost any shape --
naive, already UTC, in exchange-local time, in a vendor's arbitrary
timezone. This module is the one place that turns a raw timestamp into
this project's canonical form -- a timezone-aware pandas Timestamp in
UTC -- and attributes it to a CME trading date and to whichever of the
Asia/Europe/New York session windows (zero, one, or two -- Europe/New
York overlap) contain it.

Deliberately does NOT touch price/volume data or validate bar content --
that's the ingestion validation layer's job (src/ingest/validate.py),
not this one.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

from .exchange import UTC, CMEEquityCalendar
from .sessions import SessionWindow, build_day_sessions


def to_utc_timestamp(
    raw: dt.datetime | pd.Timestamp, source_tz: str | None = None
) -> pd.Timestamp:
    """Normalize a raw timestamp to a timezone-aware UTC pandas Timestamp.

    Raises ValueError for a naive datetime/Timestamp with no `source_tz`
    given -- this module never guesses which timezone a naive timestamp
    is in. If `raw` is already timezone-aware, `source_tz` is ignored
    (the existing tzinfo is authoritative).
    """
    ts = pd.Timestamp(raw)
    if ts.tzinfo is None:
        if source_tz is None:
            raise ValueError(
                "naive timestamp given with no source_tz -- refusing to "
                "guess which timezone it's in"
            )
        ts = ts.tz_localize(ZoneInfo(source_tz))
    return ts.tz_convert(UTC)


class NoTradingDayFoundError(ValueError):
    """Raised when a UTC timestamp doesn't fall inside any CME Globex
    trading session found within the search window -- e.g. it's sitting
    in a holiday gap, or it's bad/corrupt data far from any real
    session."""


def trading_date_for_timestamp(
    utc_ts: pd.Timestamp, calendar: CMEEquityCalendar, search_days: int = 3
) -> dt.date:
    """Find the CME trading date whose Globex session [open, close) contains utc_ts.

    Searches candidate calendar dates from `utc_ts.date() - search_days`
    to `utc_ts.date() + search_days` -- necessary because a trading
    date's session opens the evening *before* its own calendar date
    (e.g. Monday's session opens Sunday 5pm CT) -- and returns whichever
    candidate's actual Globex bounds contain utc_ts.

    Raises NoTradingDayFoundError if no candidate in that window
    contains utc_ts.
    """
    center = utc_ts.date()
    for offset in range(-search_days, search_days + 1):
        candidate = center + dt.timedelta(days=offset)
        day = calendar.trading_day_bounds(candidate)
        if day is None:
            continue
        if day.open_utc <= utc_ts < day.close_utc:
            return day.trading_date
    raise NoTradingDayFoundError(
        f"{utc_ts} does not fall inside any CME Globex trading session "
        f"within {search_days} day(s) of {center}"
    )


def sessions_containing_timestamp(
    utc_ts: pd.Timestamp, calendar: CMEEquityCalendar
) -> list[SessionWindow]:
    """Which of the Asia/Europe/New York session windows (sessions.py)
    contain utc_ts, for the CME trading date utc_ts belongs to.

    Returns an empty list if utc_ts falls in Globex trading time that
    isn't inside any of the three defined regional windows (e.g. the gap
    between Asia close and Europe open). Can return two entries during
    the London/New York overlap.
    """
    trading_date = trading_date_for_timestamp(utc_ts, calendar)
    day_sessions = build_day_sessions(trading_date, calendar)
    if day_sessions is None:
        return []
    return [s for s in day_sessions.values() if s.utc_open <= utc_ts < s.utc_close]
