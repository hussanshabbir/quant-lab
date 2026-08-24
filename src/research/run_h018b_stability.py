"""H018b follow-up: year-by-year stability check on the vol-persistence
finding, same rigor as every other survived result in this project.
Uses the primary threshold=1.5, horizon=5d variant (the least extreme of
the 4 that survived, most conservative choice to check).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.research.data_split import DISCOVERY_END, DISCOVERY_START  # noqa: E402

VIX_PATH = Path("data/raw/vix/vix_history.csv")
BARS_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")

THRESHOLD = 1.5
HORIZON = 5


def main() -> int:
    vix = pd.read_csv(VIX_PATH)
    vix["date"] = pd.to_datetime(vix["DATE"], format="%m/%d/%Y").dt.date
    vix = vix[["date", "CLOSE"]].rename(columns={"CLOSE": "vix_close"}).sort_values("date")

    bars = pd.read_parquet(BARS_PATH)
    daily = bars.groupby("trading_date")["close"].last().sort_index().rename("close").to_frame()
    daily.index.name = "date"
    daily = daily.reset_index()
    daily["log_return"] = np.log(daily["close"] / daily["close"].shift(1))
    daily["abs_return"] = daily["log_return"].abs()

    merged = daily.merge(vix, on="date", how="inner").sort_values("date").reset_index(drop=True)
    merged["implied_move"] = merged["vix_close"].shift(1) / 16.0
    merged["ratio"] = merged["abs_return"] / (merged["implied_move"] / 100.0)
    merged[f"fwd_vol_{HORIZON}d"] = merged["abs_return"].shift(-1).rolling(HORIZON, min_periods=HORIZON).mean().shift(-(HORIZON - 1))
    merged["year"] = pd.to_datetime(merged["date"].astype(str)).dt.year

    disc = merged[(merged["date"] >= DISCOVERY_START) & (merged["date"] <= DISCOVERY_END)].copy()
    disc = disc.dropna(subset=["ratio", f"fwd_vol_{HORIZON}d"])

    baseline_by_year = disc.groupby("year")[f"fwd_vol_{HORIZON}d"].mean() * 10000

    print(f"=== BY YEAR: ratio>={THRESHOLD}, horizon={HORIZON}d ===")
    print(f"{'Year':<6}{'n_trigger':<11}{'trigger_fwd_vol':<18}{'year_baseline':<16}{'lift':<10}")
    trigger_counts_by_year = []
    for year in sorted(disc["year"].unique()):
        sub = disc[disc["year"] == year]
        trig = sub[sub["ratio"] >= THRESHOLD]
        n = len(trig)
        trigger_counts_by_year.append(n)
        if n < 3:
            print(f"{year:<6}{n:<11}{'--':<18}{baseline_by_year[year]:<16.1f}{'too few':<10}")
            continue
        trig_vol = trig[f"fwd_vol_{HORIZON}d"].mean() * 10000
        base = baseline_by_year[year]
        print(f"{year:<6}{n:<11}{trig_vol:<18.1f}{base:<16.1f}{trig_vol-base:+.1f}")

    print(f"\nYears with zero trigger days: {sum(1 for c in trigger_counts_by_year if c==0)} / {len(trigger_counts_by_year)}")
    print("(a truly persistent phenomenon should have SOME trigger days in most years, not be concentrated in a handful)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
