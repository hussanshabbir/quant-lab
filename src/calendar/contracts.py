"""ES quarterly futures contract master (blueprint Phase 48).

"48 -- Contract handling: maintain contract master (expiration, last
trade, volume, open interest, settlement, roll date). Never blindly
splice contracts."

This module builds the STATIC half of that: contract symbols and their
last-trade dates, derived purely from CME's published contract rule (no
market data required, so this is buildable before Phase 46 data
ingestion). The DYNAMIC half -- open interest, volume, and the actual
roll date -- depends on real market data and lives in ``roll.py``.

ES CONTRACT RULE (verified against CME's own contract specs and
cross-checked against a live reference source for ESU6/ESZ6):

  * Quarterly only: March (H), June (M), September (U), December (Z).
    There are no serial/monthly ES futures contracts (unlike ES
    options, which do have serial months).
  * Last trading day is the third Friday of the contract month.
  * Trading in the expiring contract terminates at 8:30 AM Central Time
    that morning (not end of day) -- final settlement is cash, against
    the Special Opening Quotation (SOQ) computed from the S&P 500
    constituents' opening prices that morning. This matters for session
    construction: on an expiration Friday, the *expiring* contract's
    "New York session" as defined in ``sessions.py`` does not actually
    exist -- that contract stopped trading before the New York session
    window even opens. Anything consuming this contract master should
    treat expiration-day session data for the expiring symbol as absent
    after 8:30 CT, not as a normal truncated session.
  * If the nominal third Friday is not a CME trading day (a full
    holiday), the last trading day rolls back to the preceding CME
    trading day -- standard futures-industry convention. In ES's
    specific case this is a theoretical safeguard rather than an
    observed event in the years checked (Good Friday and the 3rd Friday
    of March/June/Sept/Dec have not coincided), but it's cheap and
    correct to implement rather than assume it can't happen.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from .exchange import UTC

_CHICAGO = ZoneInfo("America/Chicago")
_SOQ_TERMINATION_LOCAL = dt.time(8, 30)

QUARTERLY_MONTH_CODES: dict[int, str] = {3: "H", 6: "M", 9: "U", 12: "Z"}


class TradingDayCalendar(Protocol):
    """The only calendar capability this module needs -- kept as a
    narrow Protocol rather than importing CMEEquityCalendar directly, so
    tests can pass a minimal fake without spinning up the real one."""

    def is_trading_day(self, date: dt.date) -> bool: ...


@dataclass(frozen=True)
class FuturesContract:
    """One ES quarterly contract's static reference data."""

    symbol: str  # e.g. "ESH26"
    root: str
    contract_month: int  # 3, 6, 9, or 12
    contract_year: int
    last_trade_date: dt.date
    last_trade_terminates_utc: pd.Timestamp
    tick_size: float = 0.25
    multiplier: int = 50
    settlement: str = "cash, Special Opening Quotation (SOQ)"


def _third_friday(year: int, month: int) -> dt.date:
    first_of_month = dt.date(year, month, 1)
    days_to_friday = (4 - first_of_month.weekday()) % 7  # Monday=0 ... Friday=4
    first_friday = first_of_month + dt.timedelta(days=days_to_friday)
    return first_friday + dt.timedelta(weeks=2)


def _adjusted_last_trade_date(nominal: dt.date, calendar: TradingDayCalendar) -> dt.date:
    """Roll back to the preceding CME trading day if the nominal date isn't one."""
    date = nominal
    while not calendar.is_trading_day(date):
        date -= dt.timedelta(days=1)
    return date


def build_contract(year: int, month: int, calendar: TradingDayCalendar) -> FuturesContract:
    """Build the reference-data record for one ES quarterly contract."""
    if month not in QUARTERLY_MONTH_CODES:
        raise ValueError(
            f"ES only lists quarterly contracts (Mar/Jun/Sep/Dec); got month={month}"
        )

    nominal = _third_friday(year, month)
    last_trade_date = _adjusted_last_trade_date(nominal, calendar)

    local_termination = dt.datetime.combine(
        last_trade_date, _SOQ_TERMINATION_LOCAL, tzinfo=_CHICAGO
    )
    terminates_utc = pd.Timestamp(local_termination).tz_convert(UTC)

    month_code = QUARTERLY_MONTH_CODES[month]
    year_digits = year % 100
    symbol = f"ES{month_code}{year_digits:02d}"

    return FuturesContract(
        symbol=symbol,
        root="ES",
        contract_month=month,
        contract_year=year,
        last_trade_date=last_trade_date,
        last_trade_terminates_utc=terminates_utc,
    )


def quarterly_contracts(
    start_year: int, end_year: int, calendar: TradingDayCalendar
) -> list[FuturesContract]:
    """All ES quarterly contracts from start_year through end_year, sorted by expiration."""
    contracts = [
        build_contract(year, month, calendar)
        for year in range(start_year, end_year + 1)
        for month in QUARTERLY_MONTH_CODES
    ]
    return sorted(contracts, key=lambda c: c.last_trade_date)
