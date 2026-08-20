"""Tests for src.calendar.contracts (ES quarterly contract master)."""

import datetime as dt

import pytest

from src.calendar.contracts import (
    QUARTERLY_MONTH_CODES,
    build_contract,
    quarterly_contracts,
)


class _AllTradingDaysCalendar:
    """Fake calendar: every date is a trading day. Isolates contract-date
    math from the real CME holiday calendar."""

    def is_trading_day(self, date: dt.date) -> bool:
        return True


class _ExcludesOneDateCalendar:
    """Fake calendar reporting one specific date as a non-trading day,
    to test the backward-adjustment logic without needing a real
    historical coincidence of Good Friday and a 3rd Friday."""

    def __init__(self, excluded: dt.date):
        self._excluded = excluded

    def is_trading_day(self, date: dt.date) -> bool:
        return date != self._excluded


@pytest.fixture
def calendar() -> _AllTradingDaysCalendar:
    return _AllTradingDaysCalendar()


@pytest.mark.parametrize(
    "year,month,expected_last_trade,expected_symbol",
    [
        (2026, 3, dt.date(2026, 3, 20), "ESH26"),
        (2026, 6, dt.date(2026, 6, 19), "ESM26"),
        (2026, 9, dt.date(2026, 9, 18), "ESU26"),
        (2026, 12, dt.date(2026, 12, 18), "ESZ26"),
        (2025, 12, dt.date(2025, 12, 19), "ESZ25"),
    ],
)
def test_known_expiration_dates_and_symbols(
    calendar, year, month, expected_last_trade, expected_symbol
):
    contract = build_contract(year, month, calendar)
    assert contract.last_trade_date == expected_last_trade
    assert contract.symbol == expected_symbol


def test_last_trade_terminates_at_0830_chicago_in_utc(calendar):
    # December: Chicago on standard time (CST, UTC-6) -> 08:30 CT == 14:30 UTC.
    winter = build_contract(2025, 12, calendar)
    assert winter.last_trade_terminates_utc.hour == 14
    assert winter.last_trade_terminates_utc.minute == 30

    # June: Chicago on daylight time (CDT, UTC-5) -> 08:30 CT == 13:30 UTC.
    summer = build_contract(2026, 6, calendar)
    assert summer.last_trade_terminates_utc.hour == 13
    assert summer.last_trade_terminates_utc.minute == 30


def test_non_quarterly_month_is_rejected(calendar):
    with pytest.raises(ValueError):
        build_contract(2026, 1, calendar)


def test_last_trade_date_rolls_back_when_nominal_date_is_a_holiday():
    nominal_third_friday = dt.date(2026, 3, 20)
    calendar = _ExcludesOneDateCalendar(excluded=nominal_third_friday)
    contract = build_contract(2026, 3, calendar)
    assert contract.last_trade_date == dt.date(2026, 3, 19)


def test_quarterly_contracts_are_sorted_and_cover_full_range(calendar):
    contracts = quarterly_contracts(2025, 2026, calendar)
    assert len(contracts) == 2 * len(QUARTERLY_MONTH_CODES)
    dates = [c.last_trade_date for c in contracts]
    assert dates == sorted(dates)
    assert contracts[0].symbol == "ESH25"
    assert contracts[-1].symbol == "ESZ26"
