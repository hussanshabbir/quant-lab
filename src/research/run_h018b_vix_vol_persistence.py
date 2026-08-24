"""H018b: realized/implied divergence -> subsequent volatility persistence
(risk-awareness reading, distinct from H018's directional-continuation
reading, which died). Pre-registered before running.

  Same trigger as H018: ratio(t) = realized_move(t) / (VIX_close(t-1)/16) >= threshold
  Outcome: forward realized volatility, avg(|log_return|) over the next H
  trading days, vs the same permutation-null baseline used throughout.
  Hypothesis: trigger days are followed by ELEVATED subsequent volatility
  (vol clustering/persistence), not a directional prediction.

  Thresholds: 1.5, 2.0 (same as H018). Horizons: 5, 10 trading days
  (pre-declared -- "next week" and "next two weeks" of elevated risk).
  Correction: Bonferroni + BH across all 4 variants.
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

VIX_PATH = Path("data/raw/vix/vix_history.csv")
BARS_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")
OUT_PATH = Path("data/raw/vix/h018b_results.json")

THRESHOLDS = [1.5, 2.0]
HORIZONS = [5, 10]
N_PERM = 2000
ALPHA = 0.05


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

    disc = merged[(merged["date"] >= DISCOVERY_START) & (merged["date"] <= DISCOVERY_END)].copy()
    print(f"Discovery merged ES+VIX days: {len(disc)}")

    for h in HORIZONS:
        # forward avg |return| over the NEXT h days, excluding day t itself
        disc[f"fwd_vol_{h}d"] = disc["abs_return"].shift(-1).rolling(h, min_periods=h).mean().shift(-(h - 1))

    rng = np.random.default_rng(777)
    results = []
    for threshold in THRESHOLDS:
        for h in HORIZONS:
            col = f"fwd_vol_{h}d"
            sub = disc.dropna(subset=["ratio", col])
            trigger = sub["ratio"] >= threshold
            n = int(trigger.sum())
            if n < 30:
                results.append({"threshold": threshold, "horizon_days": h, "note": "too few trigger days"})
                continue

            observed_mean = float(sub.loc[trigger, col].mean())
            all_fwd = sub[col].to_numpy()
            n_total = len(sub)
            null_means = np.empty(N_PERM)
            for i in range(N_PERM):
                idx = rng.choice(n_total, size=n, replace=False)
                null_means[i] = all_fwd[idx].mean()
            null_mean = float(null_means.mean())
            extremity = np.abs(null_means - null_mean)
            obs_extremity = abs(observed_mean - null_mean)
            p_value = (1 + np.sum(extremity >= obs_extremity)) / (N_PERM + 1)

            results.append({
                "threshold": threshold, "horizon_days": h, "n_trigger_days": n,
                "observed_fwd_avg_abs_return_bps": observed_mean * 10000,
                "permutation_null_mean_bps": null_mean * 10000,
                "lift_bps": (observed_mean - null_mean) * 10000,
                "p_value_raw": float(p_value),
            })

    p_values = [r["p_value_raw"] for r in results if "p_value_raw" in r]
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

    print("\n=== H018b RESULTS (volatility persistence, not direction) ===")
    for r in results:
        if "note" in r:
            print(r)
            continue
        print(f"ratio>={r['threshold']}, horizon={r['horizon_days']}d: n={r['n_trigger_days']}, "
              f"fwd_vol={r['observed_fwd_avg_abs_return_bps']:.1f}bps/day, null={r['permutation_null_mean_bps']:.1f}bps/day, "
              f"lift={r['lift_bps']:+.1f}bps, p={r['p_value_raw']:.4f}, "
              f"bonf={'Y' if r['survives_bonferroni'] else 'N'}, bh={'Y' if r['survives_bh'] else 'N'}")

    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
