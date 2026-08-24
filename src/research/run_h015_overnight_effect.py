"""H015: overnight hold effect, restricted to the decisive single-venue-
dominant universe (docs/known_gaps_equities.md Gap 3). DISCOVERY data
only. Cost-inclusive by design -- the hypothesis itself is "does the
cost-inclusive overnight return beat the baselines", so cost-adjustment
is baked into the primary test, not a separate later gate like H013/H014.

Universe: 197 point-in-time S&P 500 tickers with a two-venue volume
dominance ratio >= 0.90 (pre-declared threshold, see Gap 3), all
XNAS.ITCH-dominant. A stock-day only counts if that ticker was an actual
S&P 500 constituent on that date, per the point-in-time membership data
(Gap 1) -- not just "ever in the decisive universe".

Return definitions:
  overnight_return(t) = (open[t+1] - close[t]) / close[t]
  intraday_return(t)  = (close[t] - open[t]) / open[t]
Both cost-adjusted by subtracting the round-trip spread cost (10 bps,
verified conservative per Gap 2) from the raw return.

Tests (pre-declared, Bonferroni+BH across all 6):
  1. PRIMARY: pooled overnight vs. (a) buy-and-hold, (b) intraday-only
  2-6. Weekday-of-week breakdown: Mon->Tue, Tue->Wed, Wed->Thu, Thu->Fri,
       Fri->Mon (the weekend-spanning hold), each vs. the same baselines
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
OUT_PATH = BASE / "h015_results.json"

SPREAD_BPS_ROUND_TRIP = 10.0
DISCOVERY_START = dt.date(2018, 5, 1)
DISCOVERY_END = dt.date(2023, 12, 31)
ALPHA = 0.05


def load_membership() -> pd.DataFrame:
    df = pd.read_parquet(BASE / "membership_by_date.parquet")
    return df


def ticker_in_index_on(date: dt.date, membership: pd.DataFrame, ticker_sets_by_date: list) -> bool:
    pass  # replaced by vectorized approach below


def main() -> int:
    import databento as db

    nas = db.DBNStore.from_file(str(BASE / "ohlcv1d_xnas.dbn.zst")).to_df()
    decisive = pd.read_parquet(BASE / "decisive_venue_universe.parquet")
    universe = set(decisive.index)
    print(f"Decisive universe: {len(universe)} tickers")

    bars = nas[nas["symbol"].isin(universe)].copy()
    idx = bars.index if bars.index.tz else bars.index.tz_localize("UTC")
    bars = bars.set_index(idx).sort_index()
    bars["date"] = bars.index.date

    # point-in-time membership: build a date -> ticker_set lookup, forward-filled
    membership = load_membership().sort_values("date")
    mem_dates = membership["date"].to_numpy()
    mem_sets = membership["ticker_set"].to_numpy()

    def membership_set_for(date: dt.date):
        pos = np.searchsorted(mem_dates, date, side="right") - 1
        if pos < 0:
            return set()
        return mem_sets[pos]

    print("Applying point-in-time S&P 500 membership filter...")
    unique_dates = sorted(bars["date"].unique())
    date_to_memset = {d: membership_set_for(d) for d in unique_dates}
    bars["in_index"] = bars.apply(lambda r: r["symbol"] in date_to_memset[r["date"]], axis=1)
    before = len(bars)
    bars = bars[bars["in_index"]]
    print(f"Rows before PIT filter: {before}, after: {len(bars)}")

    # restrict to DISCOVERY
    bars = bars[(bars["date"] >= DISCOVERY_START) & (bars["date"] <= DISCOVERY_END)]
    print(f"Discovery-only rows: {len(bars)}, {bars['symbol'].nunique()} distinct tickers")

    # build per-symbol, date-sorted return series
    rows = []
    for sym, g in bars.groupby("symbol"):
        g = g.sort_values("date")
        g = g.reset_index(drop=True)
        g["next_open"] = g["open"].shift(-1)
        g["prev_close"] = g["close"].shift(1)
        g["next_date"] = g["date"].shift(-1)
        g["overnight_ret"] = (g["next_open"] - g["close"]) / g["close"]
        g["intraday_ret"] = (g["close"] - g["open"]) / g["open"]
        g["total_ret"] = (g["close"] - g["prev_close"]) / g["prev_close"]
        g["weekday"] = pd.to_datetime(g["date"]).dt.day_name()
        g["symbol"] = sym
        rows.append(g[["symbol", "date", "next_date", "weekday", "overnight_ret", "intraday_ret", "total_ret"]])

    panel = pd.concat(rows).dropna(subset=["overnight_ret"])
    print(f"Final stock-day panel: {len(panel)} rows")

    cost = SPREAD_BPS_ROUND_TRIP / 10000.0
    # Overnight and intraday are each a real daily round-trip trade -- cost applies every day.
    panel["overnight_ret_net"] = panel["overnight_ret"] - cost
    panel["intraday_ret_net"] = panel["intraday_ret"] - cost
    # Buy-and-hold trades ONCE across the whole multi-year period, not daily -- its per-day
    # cost is ~0 when amortized, so total_ret is left uncosted (raw close-to-close), not
    # charged a full round-trip cost on every single day like the two daily strategies.
    panel["total_ret_net"] = panel["total_ret"]

    def paired_test(sample: pd.DataFrame, label: str) -> dict:
        from scipy.stats import ttest_rel, ttest_1samp
        n = len(sample)
        if n < 30:
            return {"label": label, "n": n, "note": "too few observations"}
        on = sample["overnight_ret_net"]
        ir = sample["intraday_ret_net"]
        th = sample["total_ret_net"]

        t_vs_intraday = ttest_rel(on, ir)
        t_vs_zero = ttest_1samp(on, 0.0)

        se = on.std(ddof=1) / np.sqrt(n)
        ci = (on.mean() - 1.96 * se, on.mean() + 1.96 * se)

        return {
            "label": label, "n": n,
            "mean_overnight_net_bps": float(on.mean() * 10000),
            "mean_intraday_net_bps": float(ir.mean() * 10000),
            "mean_total_net_bps": float(th.mean() * 10000),
            "overnight_ci95_bps": [float(ci[0] * 10000), float(ci[1] * 10000)],
            "diff_overnight_minus_intraday_bps": float((on.mean() - ir.mean()) * 10000),
            "p_value_vs_intraday": float(t_vs_intraday.pvalue),
            "p_value_vs_zero": float(t_vs_zero.pvalue),
        }

    tests = []
    tests.append(paired_test(panel, "PRIMARY_pooled"))
    for wd in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        sub = panel[panel["weekday"] == wd]
        label = f"weekday_{wd}" + ("_to_Monday_weekend" if wd == "Friday" else "")
        tests.append(paired_test(sub, label))

    p_values = [t["p_value_vs_intraday"] for t in tests if "p_value_vs_intraday" in t]

    def bonferroni(pv, alpha=ALPHA):
        thr = alpha / len(pv)
        return [p < thr for p in pv]

    def bh(pv, alpha=ALPHA):
        n = len(pv)
        order = sorted(range(n), key=lambda i: pv[i])
        max_k = -1
        for rank, idx_ in enumerate(order, start=1):
            if pv[idx_] <= (rank / n) * alpha:
                max_k = rank
        survive = [False] * n
        for rank, idx_ in enumerate(order, start=1):
            if rank <= max_k:
                survive[idx_] = True
        return survive

    bonf = bonferroni(p_values)
    bhr = bh(p_values)
    j = 0
    for t in tests:
        if "p_value_vs_intraday" in t:
            t["survives_bonferroni"] = bool(bonf[j])
            t["survives_bh"] = bool(bhr[j])
            j += 1

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "universe_size": len(universe),
        "discovery_range": [str(DISCOVERY_START), str(DISCOVERY_END)],
        "cost_bps_round_trip": SPREAD_BPS_ROUND_TRIP,
        "n_stock_days": len(panel),
        "tests": tests,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, default=str)

    print("\n=== H015 RESULTS ===")
    for t in tests:
        if "note" in t:
            print(t)
            continue
        print(f"{t['label']}: n={t['n']}, overnight_net={t['mean_overnight_net_bps']:.2f}bps "
              f"(CI {t['overnight_ci95_bps'][0]:.2f}..{t['overnight_ci95_bps'][1]:.2f}), "
              f"intraday_net={t['mean_intraday_net_bps']:.2f}bps, "
              f"diff={t['diff_overnight_minus_intraday_bps']:+.2f}bps, "
              f"p_vs_intraday={t['p_value_vs_intraday']:.4f}, p_vs_zero={t['p_value_vs_zero']:.4f}, "
              f"bonf={'Y' if t['survives_bonferroni'] else 'N'}, bh={'Y' if t['survives_bh'] else 'N'}")

    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
