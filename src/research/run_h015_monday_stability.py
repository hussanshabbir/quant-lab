"""H015 follow-up: year-by-year and ticker-concentration stability check
on the Monday->Tuesday overnight effect, mirroring the Phase 64 rigor
already applied to H001-H012's strong group before it was trusted.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BASE = Path("data/raw/sp500_membership")
OUT_PATH = BASE / "h015_monday_stability_results.json"

SPREAD_BPS_ROUND_TRIP = 10.0
DISCOVERY_START = dt.date(2018, 5, 1)
DISCOVERY_END = dt.date(2023, 12, 31)


def build_panel() -> pd.DataFrame:
    import databento as db

    nas = db.DBNStore.from_file(str(BASE / "ohlcv1d_xnas.dbn.zst")).to_df()
    decisive = pd.read_parquet(BASE / "decisive_venue_universe.parquet")
    universe = set(decisive.index)

    bars = nas[nas["symbol"].isin(universe)].copy()
    idx = bars.index if bars.index.tz else bars.index.tz_localize("UTC")
    bars = bars.set_index(idx).sort_index()
    bars["date"] = bars.index.date

    membership = pd.read_parquet(BASE / "membership_by_date.parquet").sort_values("date")
    mem_dates = membership["date"].to_numpy()
    mem_sets = membership["ticker_set"].to_numpy()

    def membership_set_for(date):
        pos = np.searchsorted(mem_dates, date, side="right") - 1
        return mem_sets[pos] if pos >= 0 else set()

    unique_dates = sorted(bars["date"].unique())
    date_to_memset = {d: membership_set_for(d) for d in unique_dates}
    bars["in_index"] = bars.apply(lambda r: r["symbol"] in date_to_memset[r["date"]], axis=1)
    bars = bars[bars["in_index"]]
    bars = bars[(bars["date"] >= DISCOVERY_START) & (bars["date"] <= DISCOVERY_END)]

    rows = []
    for sym, g in bars.groupby("symbol"):
        g = g.sort_values("date").reset_index(drop=True)
        g["next_open"] = g["open"].shift(-1)
        g["overnight_ret"] = (g["next_open"] - g["close"]) / g["close"]
        g["weekday"] = pd.to_datetime(g["date"]).dt.day_name()
        g["symbol"] = sym
        g["year"] = pd.to_datetime(g["date"]).dt.year
        rows.append(g[["symbol", "date", "year", "weekday", "overnight_ret"]])

    panel = pd.concat(rows).dropna(subset=["overnight_ret"])
    cost = SPREAD_BPS_ROUND_TRIP / 10000.0
    panel["overnight_ret_net"] = panel["overnight_ret"] - cost
    return panel


def main() -> int:
    panel = build_panel()
    monday = panel[panel["weekday"] == "Monday"].copy()
    print(f"Monday->Tuesday panel: {len(monday)} stock-days, {monday['symbol'].nunique()} tickers")

    from scipy.stats import ttest_1samp

    # --- Year-by-year stability ---
    by_year = {}
    for year in sorted(monday["year"].unique()):
        sub = monday[monday["year"] == year]
        n = len(sub)
        if n < 30:
            by_year[int(year)] = {"n": n, "note": "too few"}
            continue
        mean_bps = sub["overnight_ret_net"].mean() * 10000
        se = sub["overnight_ret_net"].std(ddof=1) / np.sqrt(n)
        ci = (mean_bps - 1.96 * se * 10000, mean_bps + 1.96 * se * 10000)
        p = ttest_1samp(sub["overnight_ret_net"], 0.0).pvalue
        by_year[int(year)] = {"n": n, "mean_bps": float(mean_bps), "ci95_bps": [float(ci[0]), float(ci[1])], "p_vs_zero": float(p)}

    print("\n=== BY YEAR ===")
    for year, s in by_year.items():
        if "note" in s:
            print(year, s)
            continue
        print(f"{year}: n={s['n']}, mean={s['mean_bps']:.2f}bps, CI=[{s['ci95_bps'][0]:.2f},{s['ci95_bps'][1]:.2f}], p={s['p_vs_zero']:.4f}")

    # --- Ticker concentration ---
    per_ticker = monday.groupby("symbol").agg(
        n=("overnight_ret_net", "count"),
        mean_bps=("overnight_ret_net", lambda x: x.mean() * 10000),
        total_bps=("overnight_ret_net", lambda x: x.sum() * 10000),
    ).sort_values("total_bps", ascending=False)

    n_positive_mean = (per_ticker["mean_bps"] > 0).sum()
    n_total_tickers = len(per_ticker)
    print(f"\n=== TICKER CONCENTRATION ===")
    print(f"Tickers with positive mean Monday overnight return: {n_positive_mean} / {n_total_tickers} ({n_positive_mean/n_total_tickers:.1%})")

    overall_sum_bps = monday["overnight_ret_net"].sum() * 10000
    top10_sum = per_ticker["total_bps"].head(10).sum()
    print(f"Top 10 tickers' share of total summed effect: {top10_sum/overall_sum_bps:.1%}" if overall_sum_bps != 0 else "N/A")
    print("\nTop 10 contributors:")
    print(per_ticker.head(10))
    print("\nBottom 10 (most negative) contributors:")
    print(per_ticker.tail(10))

    # leave-out robustness: recompute excluding top 10 positive contributors
    top10_symbols = per_ticker.head(10).index.tolist()
    excl = monday[~monday["symbol"].isin(top10_symbols)]
    excl_mean = excl["overnight_ret_net"].mean() * 10000
    excl_p = ttest_1samp(excl["overnight_ret_net"], 0.0).pvalue
    print(f"\nExcluding top 10 contributors: n={len(excl)}, mean={excl_mean:.2f}bps, p={excl_p:.4f}")

    # churn check: full-period tickers (present in >= 90% of possible Mondays) vs partial
    max_possible = monday.groupby("symbol")["date"].nunique().max()
    full_period_syms = per_ticker[per_ticker["n"] >= 0.9 * max_possible].index
    partial_syms = per_ticker[per_ticker["n"] < 0.9 * max_possible].index
    full_sub = monday[monday["symbol"].isin(full_period_syms)]
    partial_sub = monday[monday["symbol"].isin(partial_syms)]
    print(f"\n=== CHURN CHECK ===")
    print(f"Full-period tickers (>=90% of max Mondays): {len(full_period_syms)}, n_obs={len(full_sub)}, "
          f"mean={full_sub['overnight_ret_net'].mean()*10000:.2f}bps, p={ttest_1samp(full_sub['overnight_ret_net'],0.0).pvalue:.4f}")
    print(f"Partial/churned tickers: {len(partial_syms)}, n_obs={len(partial_sub)}, "
          f"mean={partial_sub['overnight_ret_net'].mean()*10000:.2f}bps, p={ttest_1samp(partial_sub['overnight_ret_net'],0.0).pvalue:.4f}")

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "by_year": by_year,
        "n_tickers_positive_mean": int(n_positive_mean),
        "n_tickers_total": int(n_total_tickers),
        "top10_contributors": per_ticker.head(10).to_dict(orient="index"),
        "excl_top10_mean_bps": float(excl_mean),
        "excl_top10_p": float(excl_p),
        "full_period_n_tickers": len(full_period_syms),
        "full_period_mean_bps": float(full_sub["overnight_ret_net"].mean() * 10000),
        "full_period_p": float(ttest_1samp(full_sub["overnight_ret_net"], 0.0).pvalue),
        "partial_n_tickers": len(partial_syms),
        "partial_mean_bps": float(partial_sub["overnight_ret_net"].mean() * 10000),
        "partial_p": float(ttest_1samp(partial_sub["overnight_ret_net"], 0.0).pvalue),
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
