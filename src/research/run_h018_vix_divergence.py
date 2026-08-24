"""H018: realized ES move vs VIX-implied move divergence -> next-day
direction. DISCOVERY data only. Pre-registered before running -- see the
chat message accompanying this script for full design rationale.

  implied_move(t) = VIX_close(t-1) / 16   (yesterday's close, no lookahead,
                                            matches "before market opens")
  realized_move(t) = |ES daily log return(t)|
  ratio(t) = realized_move(t) / implied_move(t)

  Trigger, 2 pre-declared thresholds: ratio(t) >= 1.5 or >= 2.0
  Outcome, 2 pre-declared horizons: does sign(return(t+H)) == sign(return(t))
    for H in {1, 5} trading days -- i.e. does the surprise move continue?

  Baseline: permutation (shuffle trigger-day labels, preserve actual
  return-sign sequence), N=2000.
  Correction: Bonferroni + BH across all 4 (threshold x horizon) variants.
  Gate: trading-sim/cost step only if something survives correction.
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
OUT_PATH = Path("data/raw/vix/h018_results.json")

THRESHOLDS = [1.5, 2.0]
HORIZONS = [1, 5]
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

    merged = daily.merge(vix, on="date", how="inner").sort_values("date").reset_index(drop=True)
    merged["implied_move"] = merged["vix_close"].shift(1) / 16.0  # yesterday's VIX, no lookahead
    merged["realized_move"] = merged["log_return"].abs()
    merged["ratio"] = merged["realized_move"] / (merged["implied_move"] / 100.0)  # VIX in % points

    disc = merged[(merged["date"] >= DISCOVERY_START) & (merged["date"] <= DISCOVERY_END)].copy()
    print(f"Discovery merged ES+VIX days: {len(disc)}")

    for h in HORIZONS:
        disc[f"fwd_return_{h}d"] = disc["log_return"].shift(-h)

    rng = np.random.default_rng(555)
    results = []
    for threshold in THRESHOLDS:
        for h in HORIZONS:
            col = f"fwd_return_{h}d"
            sub = disc.dropna(subset=["ratio", "log_return", col])
            trigger = sub["ratio"] >= threshold
            n = int(trigger.sum())
            if n < 30:
                results.append({"threshold": threshold, "horizon_days": h, "note": "too few trigger days"})
                continue

            triggered = sub[trigger]
            continuation = (np.sign(triggered["log_return"]) == np.sign(triggered[col]))
            observed_rate = float(continuation.mean())

            same_sign_all = (np.sign(sub["log_return"]) == np.sign(sub[col])).to_numpy()
            n_total = len(sub)
            null_rates = np.empty(N_PERM)
            for i in range(N_PERM):
                idx = rng.choice(n_total, size=n, replace=False)
                null_rates[i] = same_sign_all[idx].mean()
            null_mean = float(null_rates.mean())
            extremity = np.abs(null_rates - null_mean)
            obs_extremity = abs(observed_rate - null_mean)
            p_value = (1 + np.sum(extremity >= obs_extremity)) / (N_PERM + 1)

            results.append({
                "threshold": threshold, "horizon_days": h, "n_trigger_days": n,
                "observed_continuation_rate": observed_rate,
                "permutation_null_mean": null_mean,
                "lift": observed_rate - null_mean,
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

    print("\n=== H018 RESULTS ===")
    for r in results:
        if "note" in r:
            print(r)
            continue
        print(f"ratio>={r['threshold']}, horizon={r['horizon_days']}d: n={r['n_trigger_days']}, "
              f"continuation_rate={r['observed_continuation_rate']:.3f}, null={r['permutation_null_mean']:.3f}, "
              f"lift={r['lift']:+.3f}, p={r['p_value_raw']:.4f}, "
              f"bonf={'Y' if r['survives_bonferroni'] else 'N'}, bh={'Y' if r['survives_bh'] else 'N'}")

    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
