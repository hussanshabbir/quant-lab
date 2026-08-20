"""Per-session OHLCV/VWAP/range geometry (blueprint Phase 50).

Computes descriptive geometry -- open, high, low, close, high/low
timestamps, volume, VWAP, range -- for one session's worth of bars.

SCOPE BOUNDARY (deliberate): this module knows nothing about another
session's levels, and nothing about touches, breaks, sweeps, or
acceptance/rejection. It answers "what happened during this window",
full stop. Hypothesis-layer logic (blueprint Phase 51+, H001-H012 --
"did price touch/break the Asia high") belongs entirely to a later,
separate module that consumes this module's output. If this file ever
starts referencing a *different* session's high/low, that's a scope
violation -- stop and reconsider.

INPUT CONTRACT: `bars` is a pandas DataFrame with either a UTC
timezone-aware DatetimeIndex, or a "timestamp" column of the same, plus
open/high/low/close/volume columns. Bar timestamps are assumed to mark
bar OPEN time (standard OHLCV convention) -- a bar belongs to a session
if `session.utc_open <= bar_timestamp < session.utc_close` (half-open:
a bar starting exactly at a session's close boundary belongs to the
NEXT session, not this one).

SESSION BOUNDARIES COME FROM THE CALENDAR LAYER, NOT FROM THE BARS.
`session.utc_open`/`session.utc_close` (a `SessionWindow` from
sessions.py) are fixed inputs -- this module filters bars to that fixed
window, it never infers the window from which bars happen to be
present. Missing bars shrink `bar_count`, never the window itself.

VWAP CONVENTION: this module only has OHLCV bars, not tick/trade data,
so VWAP here is necessarily an approximation, not ground truth:

    VWAP = sum(typical_price_i * volume_i) / sum(volume_i)
    typical_price_i = (high_i + low_i + close_i) / 3

This is a documented research-parameter choice. Phase 68 ("fill model:
upgrade bar -> tick -> quote -> order book") is the acknowledgment that
a real fill/VWAP eventually needs finer data than this.

FAILURE PHILOSOPHY: an empty session or duplicate bar timestamps raise
explicitly rather than returning a fabricated or silently-wrong
geometry -- consistent with the rest of this codebase (see
exchange.py's holiday handling, sessions.py's clip flagging).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from .sessions import SessionWindow

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


class EmptySessionError(ValueError):
    """Raised when a session window contains zero bars. Never silently
    return a fabricated/default geometry for an empty session."""


class DuplicateBarsError(ValueError):
    """Raised when more than one bar shares a timestamp within a session
    window. Never silently sum/average duplicate bars -- resolve
    duplicates upstream (src/ingest/validate.py) before computing
    geometry."""


@dataclass(frozen=True)
class SessionGeometry:
    session_name: str
    trading_date: dt.date
    utc_open: pd.Timestamp
    utc_close: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    high_time: pd.Timestamp
    low_time: pd.Timestamp
    volume: float
    vwap: float
    range: float
    bar_count: int
    zero_volume_bar_count: int


def _bar_timestamps(bars: pd.DataFrame) -> pd.DatetimeIndex:
    if isinstance(bars.index, pd.DatetimeIndex):
        idx = bars.index
    elif "timestamp" in bars.columns:
        idx = pd.DatetimeIndex(bars["timestamp"])
    else:
        raise ValueError("bars must have a DatetimeIndex or a 'timestamp' column")

    if idx.tz is None:
        raise ValueError(
            "bar timestamps must be timezone-aware (UTC) -- see "
            "calendar.timestamps.to_utc_timestamp for normalizing raw input"
        )
    return idx


def compute_session_geometry(bars: pd.DataFrame, session: SessionWindow) -> SessionGeometry:
    """Compute OHLCV/VWAP/range geometry for the bars inside `session`'s window.

    Raises EmptySessionError if no bars fall inside
    [session.utc_open, session.utc_close). Raises DuplicateBarsError if
    more than one bar shares a timestamp inside that window.
    """
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in bars.columns]
    if missing_cols:
        raise ValueError(f"bars is missing required columns: {missing_cols}")

    timestamps = _bar_timestamps(bars)
    frame = bars.copy()
    frame.index = timestamps
    frame = frame.sort_index()

    in_window = (frame.index >= session.utc_open) & (frame.index < session.utc_close)
    windowed = frame.loc[in_window]

    if windowed.empty:
        raise EmptySessionError(
            f"no bars found in session '{session.name}' window "
            f"{session.utc_open} -> {session.utc_close} "
            f"(trading_date={session.trading_date}) -- refusing to fabricate a geometry"
        )

    duplicate_mask = windowed.index.duplicated(keep=False)
    if duplicate_mask.any():
        dupes = sorted(set(windowed.index[duplicate_mask]))
        raise DuplicateBarsError(
            f"duplicate bar timestamp(s) in session '{session.name}' window: {dupes}"
        )

    open_price = float(windowed["open"].iloc[0])
    close_price = float(windowed["close"].iloc[-1])
    high_price = float(windowed["high"].max())
    low_price = float(windowed["low"].min())
    high_time = windowed["high"].idxmax()
    low_time = windowed["low"].idxmin()
    volume = float(windowed["volume"].sum())
    zero_volume_bar_count = int((windowed["volume"] == 0).sum())

    typical_price = (windowed["high"] + windowed["low"] + windowed["close"]) / 3
    weighted_sum = float((typical_price * windowed["volume"]).sum())
    vwap = weighted_sum / volume if volume > 0 else float("nan")

    return SessionGeometry(
        session_name=session.name,
        trading_date=session.trading_date,
        utc_open=session.utc_open,
        utc_close=session.utc_close,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        high_time=high_time,
        low_time=low_time,
        volume=volume,
        vwap=vwap,
        range=high_price - low_price,
        bar_count=len(windowed),
        zero_volume_bar_count=zero_volume_bar_count,
    )
