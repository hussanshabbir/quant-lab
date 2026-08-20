"""Shared context features for Phase 55-60 conditioning: trend regime,
realized-volatility regime, year, and weekday, computed from the real
continuous front-month series and joined onto session_labels rows.

Kept deliberately separate from session_labels.py's own construction (Phase
51-53) -- these are conditioning variables for slicing existing labels, not
part of the touch/break/accept/reject definitions themselves.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

BARS_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")

TREND_LOOKBACK_DAYS = 60  # ~1 quarter of trading days
VOL_LOOKBACK_DAYS = 20  # ~1 month


def build_daily_context() -> pd.DataFrame:
    """One row per real trading date: close, trailing-N-day return (trend
    proxy), trailing-N-day average daily range/close (realized-volatility
    proxy), year, weekday. All computed strictly from real bars -- no
    synthetic data."""
    bars = pd.read_parquet(BARS_PATH)
    daily = bars.groupby("trading_date").agg(
        day_open=("open", "first"), day_high=("high", "max"),
        day_low=("low", "min"), day_close=("close", "last"),
    ).sort_index()

    daily["trend_return"] = daily["day_close"].pct_change(TREND_LOOKBACK_DAYS)
    daily["trend_regime"] = np.where(daily["trend_return"] > 0, "up", "down")

    daily_range_pct = (daily["day_high"] - daily["day_low"]) / daily["day_close"]
    daily["vol_proxy"] = daily_range_pct.rolling(VOL_LOOKBACK_DAYS).mean()
    daily["vol_quintile"] = pd.qcut(daily["vol_proxy"], 5, labels=[1, 2, 3, 4, 5])

    daily["year"] = pd.to_datetime(daily.index.astype(str)).year
    daily["weekday"] = pd.to_datetime(daily.index.astype(str)).day_name()

    daily = daily.reset_index().rename(columns={"trading_date": "trading_date"})
    return daily[["trading_date", "day_close", "trend_return", "trend_regime",
                  "vol_proxy", "vol_quintile", "year", "weekday"]]


def join_context(labels: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    return labels.merge(context, on="trading_date", how="left")
