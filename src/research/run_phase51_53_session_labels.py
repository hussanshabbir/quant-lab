"""Phase 51-53: build the labeled dataset for H001-H012 -- session highs/
lows, touches, breaks, sweep order, and acceptance/rejection -- WITHOUT
computing any H001-H012 result. That's Phase 54, deliberately separate.

Two comparisons, matching the blueprint's H001-H012 definitions exactly:
  - europe_vs_asia: does Europe touch/break Asia's high/low?
  - ny_vs_europe: does New York touch/break Europe's high/low?

Per comparison, per trading date (only where BOTH sessions have real
computed geometry -- see Phase 49-50's missing-session log):
  touched_high/low: current session's bar range reached the prior level
  broke_high/low: current session's high/low exceeded the prior level
  break_high/low_time: first bar timestamp the break occurred (from real
    1-minute bars, not just the session aggregate)
  sweep_order: HIGH_FIRST / LOW_FIRST / HIGH_ONLY / LOW_ONLY / BOTH / NEITHER
    (BOTH = both broke, order indeterminate from bar-close-time ordering;
    should not occur if HIGH_FIRST/LOW_FIRST correctly cover the ordered
    case -- see note below)
  broke_high_accepted/rejected: on a high break, did the session's CLOSE
    stay above the level (accepted) or return below it (rejected) by
    session end? Mutually exclusive with each other; both False if no
    break occurred. Same logic mirrored for low breaks.

No H001-H012 statistics, no baselines, no significance testing here --
purely descriptive labeling, one row per (trading_date, comparison).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BARS_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")
GEOMETRY_PATH = Path("data/raw/es_futures/session_geometry.parquet")
OUT_PATH = Path("data/raw/es_futures/session_labels.parquet")

COMPARISONS = [
    ("europe_vs_asia", "asia", "europe"),
    ("ny_vs_europe", "europe", "new_york"),
]


def label_one(prior_geo: pd.Series, current_geo: pd.Series, current_bars: pd.DataFrame) -> dict:
    prior_high, prior_low = prior_geo["high"], prior_geo["low"]
    cur_high, cur_low, cur_close = current_geo["high"], current_geo["low"], current_geo["close"]

    touched_high = cur_high >= prior_high
    touched_low = cur_low <= prior_low
    broke_high = cur_high > prior_high
    broke_low = cur_low < prior_low

    break_high_time = None
    break_low_time = None
    if broke_high:
        break_high_time = current_bars[current_bars["high"] > prior_high].index.min()
    if broke_low:
        break_low_time = current_bars[current_bars["low"] < prior_low].index.min()

    if broke_high and broke_low:
        if break_high_time < break_low_time:
            sweep_order = "HIGH_FIRST"
        elif break_low_time < break_high_time:
            sweep_order = "LOW_FIRST"
        else:
            sweep_order = "BOTH"  # same bar broke both levels
    elif broke_high:
        sweep_order = "HIGH_ONLY"
    elif broke_low:
        sweep_order = "LOW_ONLY"
    else:
        sweep_order = "NEITHER"

    broke_high_accepted = bool(broke_high and cur_close > prior_high)
    broke_high_rejected = bool(broke_high and cur_close <= prior_high)
    broke_low_accepted = bool(broke_low and cur_close < prior_low)
    broke_low_rejected = bool(broke_low and cur_close >= prior_low)

    return {
        "prior_high": prior_high, "prior_low": prior_low,
        "current_open": current_geo["open"], "current_high": cur_high,
        "current_low": cur_low, "current_close": cur_close,
        "touched_high": bool(touched_high), "touched_low": bool(touched_low),
        "broke_high": bool(broke_high), "broke_low": bool(broke_low),
        "break_high_time": break_high_time, "break_low_time": break_low_time,
        "sweep_order": sweep_order,
        "broke_high_accepted": broke_high_accepted, "broke_high_rejected": broke_high_rejected,
        "broke_low_accepted": broke_low_accepted, "broke_low_rejected": broke_low_rejected,
    }


def main() -> int:
    bars = pd.read_parquet(BARS_PATH)
    ts_index = bars.index if bars.index.tz else bars.index.tz_localize("UTC")
    bars = bars.set_index(ts_index).sort_index()

    geo = pd.read_parquet(GEOMETRY_PATH)
    geo["trading_date"] = pd.to_datetime(geo["trading_date"]).dt.date
    geo = geo.set_index(["trading_date", "session"])

    trading_dates = sorted(bars["trading_date"].unique())
    print(f"Building session labels for {len(trading_dates)} trading dates x {len(COMPARISONS)} comparisons...")

    rows = []
    skipped_missing_geo = 0
    for trading_date in trading_dates:
        day_bars = bars[bars["trading_date"] == trading_date]
        for comparison_name, prior_name, current_name in COMPARISONS:
            try:
                prior_geo = geo.loc[(trading_date, prior_name)]
                current_geo = geo.loc[(trading_date, current_name)]
            except KeyError:
                skipped_missing_geo += 1
                continue

            current_bars = day_bars[(day_bars.index >= current_geo["utc_open"]) & (day_bars.index < current_geo["utc_close"])]
            if current_bars.empty:
                skipped_missing_geo += 1
                continue

            label = label_one(prior_geo, current_geo, current_bars)
            label["trading_date"] = trading_date
            label["comparison"] = comparison_name
            rows.append(label)

    result = pd.DataFrame(rows)
    result.to_parquet(OUT_PATH)

    print(f"\nLabeled rows: {len(result)} (skipped {skipped_missing_geo} date/comparison pairs missing session geometry)")
    print(f"\nBy comparison:")
    print(result.groupby("comparison").size())
    print(f"\nSweep order distribution:")
    print(result.groupby(["comparison", "sweep_order"]).size())
    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
