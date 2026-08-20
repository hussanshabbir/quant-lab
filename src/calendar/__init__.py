"""Exchange calendar, session, and contract-master engine (blueprint Phase 5 / 47-49 / 48).

Public API:

    CMEEquityCalendar   -- CME Globex trading-day / holiday / early-close lookups
    GlobexTradingDay     -- one CME trading date's exact UTC open/close bounds
    build_day_sessions   -- Asia/Europe/New York session windows for one trading date
    SessionWindow         -- one region's session window (local + UTC timestamps)
    SESSION_DEFINITIONS   -- the local wall-clock hours each session is defined from
    FuturesContract        -- one ES quarterly contract's static reference data
    build_contract         -- build a single FuturesContract
    quarterly_contracts    -- build all ES quarterly contracts over a year range
    RollDecision            -- a determined (or absent) contract roll date
    volume_crossover_roll_date -- determine roll date from real volume data

See docs/known_gaps.md for known limitations in the underlying calendar
data, and roll.py's module docstring for the roll engine's validation
status.
"""

from .contracts import FuturesContract, build_contract, quarterly_contracts
from .exchange import CMEEquityCalendar, GlobexTradingDay
from .roll import RollDecision, volume_crossover_roll_date
from .session_geometry import (
    DuplicateBarsError,
    EmptySessionError,
    SessionGeometry,
    compute_session_geometry,
)
from .sessions import SESSION_DEFINITIONS, SessionWindow, build_day_sessions
from .timestamps import (
    NoTradingDayFoundError,
    sessions_containing_timestamp,
    to_utc_timestamp,
    trading_date_for_timestamp,
)

__all__ = [
    "CMEEquityCalendar",
    "GlobexTradingDay",
    "build_day_sessions",
    "SessionWindow",
    "SESSION_DEFINITIONS",
    "FuturesContract",
    "build_contract",
    "quarterly_contracts",
    "RollDecision",
    "volume_crossover_roll_date",
    "to_utc_timestamp",
    "trading_date_for_timestamp",
    "sessions_containing_timestamp",
    "NoTradingDayFoundError",
    "compute_session_geometry",
    "SessionGeometry",
    "EmptySessionError",
    "DuplicateBarsError",
]
