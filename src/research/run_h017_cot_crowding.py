"""H017: COT Leveraged Funds crowding -> ES forward return (mean reversion).
DISCOVERY data only (reuses the exact data_split.py boundaries already
locked for the ES work -- same instrument, same split).

PRE-REGISTERED DESIGN (locked before running):
  Data: CFTC TFF report, "E-MINI S&P 500", lev_money_positions_long/short
  (the actual CFTC category name for hedge funds/CTAs -- the closest public
  proxy to "speculative crowding"). Free, public, weekly, 2006-2026.

  Signal: net_pct(t) = (lev_long(t) - lev_short(t)) / open_interest_all(t),
  a trailing-window PERCENTILE RANK of net_pct over the preceding
  N=104 weeks (2 years), computed using only data strictly before t (no
  lookahead). Self-calibrating threshold, not a fixed arbitrary cutoff.

  Trigger, tested at 2 pre-declared percentile thresholds (10% and 20% -- not
  swept and picked after seeing results):
    EXTREME_LONG:  percentile_rank >= (1 - threshold)
    EXTREME_SHORT: percentile_rank <= threshold

  Outcome, tested at 2 pre-declared forward horizons (1 week, 4 weeks):
    forward_return(t, H) = ES continuous-series close H weeks after the
    COT report date, vs close at the report date.

  Hypothesis (mean reversion / crowding): EXTREME_LONG predicts LOWER
  forward returns than EXTREME_SHORT -- a crowded long has more sellers
  than buyers left; a crowded short has more short-covering buyers left.

  Baseline: permutation test -- shuffle which weeks are labeled
  EXTREME_LONG/EXTREME_SHORT (preserving the actual forward-return
  sequence), N=2000, to test whether the real timing of extremes predicts
  forward returns more than random timing would.

  Correction: Bonferroni + BH across all 4 (threshold x horizon) variants.

  Gate: proceeds to trading-sim/cost testing only if something survives
  correction, same standard as every other hypothesis in this project.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.research.data_split import DISCOVERY_END, DISCOVERY_START  # noqa: E402

COT_PATH = Path("data/raw/cot/es_tff_raw.json")
BARS_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")
OUT_PATH = Path("data/raw/cot/h017_results.json")

TRAILING_WEEKS = 104
THRESHOLDS = [0.10, 0.20]
HORIZONS_WEEKS = [1, 4]
N_PERM = 2000
ALPHA = 0.05


def load_cot() -> pd.DataFrame:
    raw = json.load(open(COT_PATH))
    df = pd.DataFrame(raw)
    df["report_date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.date
    for col in ["open_interest_all", "lev_money_positions_long", "lev_money_positions_short"]:
        df[col] = df[col].astype(float)
    df = df.sort_values("report_date").reset_index(drop=True)
    df["net_pct"] = (df["lev_money_positions_long"] - df["lev_money_positions_short"]) / df["open_interest_all"]
    return df


def compute_pctile_rank(df: pd.DataFrame) -> pd.DataFrame:
    ranks = [np.nan] * len(df)
    net = df["net_pct"].to_numpy()
    for i in range(len(df)):
        window = net[max(0, i - TRAILING_WEEKS):i]  # strictly before i
        if len(window) < 52:
            continue
        ranks[i] = float((window < net[i]).mean())
    df["pctile_rank"] = ranks
    return df


def build_forward_returns(bars_daily_close: pd.Series, report_date: dt.date, horizon_weeks: int) -> float | None:
    target = report_date + dt.timedelta(weeks=horizon_weeks)
    idx = bars_daily_close.index
    on_or_after = idx[idx >= report_date]
    on_or_after_target = idx[idx >= target]
    if len(on_or_after) == 0 or len(on_or_after_target) == 0:
        return None
    start_price = bars_daily_close.loc[on_or_after[0]]
    end_price = bars_daily_close.loc[on_or_after_target[0]]
    return float((end_price - start_price) / start_price)


def main() -> int:
    cot = load_cot()
    cot = compute_pctile_rank(cot)

    bars = pd.read_parquet(BARS_PATH)
    daily_close = bars.groupby("trading_date")["close"].last().sort_index()

    cot["report_date"] = pd.to_datetime(cot["report_date"]).dt.date if cot["report_date"].dtype == object else cot["report_date"]
    disc = cot[(cot["report_date"] >= DISCOVERY_START) & (cot["report_date"] <= DISCOVERY_END)].copy()
    disc = disc.dropna(subset=["pctile_rank"])
    print(f"Discovery COT weeks with valid trailing rank: {len(disc)}")

    for h in HORIZONS_WEEKS:
        disc[f"fwd_ret_{h}w"] = disc["report_date"].apply(lambda d: build_forward_returns(daily_close, d, h))

    rng = np.random.default_rng(2024)
    results = []
    for threshold in THRESHOLDS:
        for h in HORIZONS_WEEKS:
            col = f"fwd_ret_{h}w"
            sub = disc.dropna(subset=[col])
            is_long = sub["pctile_rank"] >= (1 - threshold)
            is_short = sub["pctile_rank"] <= threshold
            n_long, n_short = int(is_long.sum()), int(is_short.sum())
            if n_long < 10 or n_short < 10:
                results.append({"threshold": threshold, "horizon_weeks": h, "note": "too few extreme weeks"})
                continue

            mean_long = float(sub.loc[is_long, col].mean())
            mean_short = float(sub.loc[is_short, col].mean())
            diff = mean_long - mean_short  # expect negative if mean-reversion holds

            # permutation: shuffle extreme labels among all discovery weeks (fixed n_long, n_short), recompute diff
            all_rets = sub[col].to_numpy()
            n_total = len(sub)
            null_diffs = np.empty(N_PERM)
            for i in range(N_PERM):
                perm = rng.permutation(n_total)
                long_idx = perm[:n_long]
                short_idx = perm[n_long:n_long + n_short]
                null_diffs[i] = all_rets[long_idx].mean() - all_rets[short_idx].mean()
            null_mean = float(null_diffs.mean())
            p_value = (1 + np.sum(np.abs(null_diffs - null_mean) >= abs(diff - null_mean))) / (N_PERM + 1)

            results.append({
                "threshold": threshold, "horizon_weeks": h,
                "n_long_extreme": n_long, "n_short_extreme": n_short,
                "mean_fwd_ret_after_long_extreme_bps": mean_long * 10000,
                "mean_fwd_ret_after_short_extreme_bps": mean_short * 10000,
                "diff_bps": diff * 10000,
                "permutation_null_mean_bps": null_mean * 10000,
                "p_value_raw": float(p_value),
                "direction_matches_reversal_hypothesis": bool(diff < 0),
            })

    p_values = [r["p_value_raw"] for r in results if "p_value_raw" in r]

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
    for r in results:
        if "p_value_raw" in r:
            r["survives_bonferroni"] = bool(bonf[j])
            r["survives_bh"] = bool(bhr[j])
            j += 1

    with open(OUT_PATH, "w") as f:
        json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "results": results}, f, indent=2, default=str)

    print("\n=== H017 RESULTS ===")
    for r in results:
        if "note" in r:
            print(r)
            continue
        print(f"threshold={r['threshold']}, horizon={r['horizon_weeks']}w: "
              f"n_long={r['n_long_extreme']}, n_short={r['n_short_extreme']}, "
              f"after_long_extreme={r['mean_fwd_ret_after_long_extreme_bps']:.1f}bps, "
              f"after_short_extreme={r['mean_fwd_ret_after_short_extreme_bps']:.1f}bps, "
              f"diff={r['diff_bps']:+.1f}bps, reversal_direction={r['direction_matches_reversal_hypothesis']}, "
              f"p={r['p_value_raw']:.4f}, bonf={'Y' if r['survives_bonferroni'] else 'N'}, bh={'Y' if r['survives_bh'] else 'N'}")

    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
