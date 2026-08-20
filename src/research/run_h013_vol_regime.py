"""H013 (blueprint Phase 23-24): volatility-regime-transition -> next-day
directional continuation/reversal. ES only, DISCOVERY data only, zero new
data pull (uses the existing continuous_front_month.parquet).

Pre-registered BEFORE running: see the chat message accompanying this
script for the full design rationale. Summary:

  Trigger: |log_return(t)| > K * trailing_20d_median(|log_return|)(t),
  baseline strictly from days < t (no lookahead). K in {1.5, 2.0, 2.5},
  2.0 primary, all three reported -- not swept-and-cherry-picked.

  Outcome: sign(log_return(t+1)) == sign(log_return(t)) (continuation).

  Baseline: unconditional continuation rate over non-trigger days in the
  same discovery set. Permutation test (shuffle trigger labels, N=2000)
  for the p-value. Sign is scale-invariant, so (unlike the touch/break
  baseline) no local-block fix is needed for price-level non-stationarity.

  Correction: Bonferroni + BH across the 3 thresholds.

  If ANY threshold survives correction: trend-regime split (up/down) and
  year-by-year stability, matching the rigor already applied to H005-H008.
  If it survives THAT too: the pre-declared trading rule (locked in this
  script, not written after seeing results) is simulated with the same
  cost model as Phase 66-70.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.research.context_features import build_daily_context  # noqa: E402
from src.research.data_split import DISCOVERY_END, DISCOVERY_START  # noqa: E402

BARS_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")
OUT_PATH = Path("data/raw/es_futures/h013_vol_regime_results.json")

THRESHOLDS = [1.5, 2.0, 2.5]
PRIMARY_THRESHOLD = 2.0
TRAILING_WINDOW = 20
N_PERM = 2000
RNG_SEED = 99
ALPHA = 0.05

# --- pre-declared trading rule (locked before any result is seen) ---
TICK_SIZE = 0.25
TICK_VALUE = 12.50
MULTIPLIER = 50.0
COMMISSION_FEES_ROUND_TURN = 4.50
SLIPPAGE_TICKS_PER_SIDE = 1
TRADE_R_MULTIPLE = 1.0


def wilson_ci(k: int, n: int, alpha: float = ALPHA) -> tuple[float, float]:
    from scipy.stats import norm
    z = norm.ppf(1 - alpha / 2)
    p = k / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return ((center - half) / denom, (center + half) / denom)


def bonferroni(p_values: list[float], alpha: float = ALPHA) -> list[bool]:
    threshold = alpha / len(p_values)
    return [p < threshold for p in p_values]


def benjamini_hochberg(p_values: list[float], alpha: float = ALPHA) -> list[bool]:
    n = len(p_values)
    order = sorted(range(n), key=lambda i: p_values[i])
    survive = [False] * n
    max_k = -1
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= (rank / n) * alpha:
            max_k = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= max_k:
            survive[idx] = True
    return survive


def build_daily_series() -> pd.DataFrame:
    bars = pd.read_parquet(BARS_PATH)
    daily = bars.groupby("trading_date").agg(
        day_open=("open", "first"), day_high=("high", "max"),
        day_low=("low", "min"), day_close=("close", "last"),
    ).sort_index()
    daily = daily[(daily.index >= DISCOVERY_START) & (daily.index <= DISCOVERY_END)]
    daily["log_return"] = np.log(daily["day_close"] / daily["day_close"].shift(1))
    daily["abs_return"] = daily["log_return"].abs()
    # trailing baseline strictly from days BEFORE t -- shift(1) before rolling
    daily["trailing_median"] = daily["abs_return"].shift(1).rolling(TRAILING_WINDOW).median()
    daily["next_log_return"] = daily["log_return"].shift(-1)
    daily["day_range"] = daily["day_high"] - daily["day_low"]
    return daily


def test_threshold(daily: pd.DataFrame, k: float, rng: np.random.Generator) -> dict:
    valid = daily.dropna(subset=["log_return", "trailing_median", "next_log_return"]).copy()
    valid["trigger"] = valid["abs_return"] > (k * valid["trailing_median"])
    valid["continuation"] = np.sign(valid["log_return"]) == np.sign(valid["next_log_return"])

    triggered = valid[valid["trigger"]]
    non_triggered = valid[~valid["trigger"]]
    n = len(triggered)
    if n < 10:
        return {"k": k, "n_trigger_days": n, "note": "too few trigger days"}

    k_cont = int(triggered["continuation"].sum())
    observed_rate = k_cont / n
    ci = wilson_ci(k_cont, n)
    baseline_rate = float(non_triggered["continuation"].mean())

    # permutation: shuffle which days are "trigger" (same count), recompute rate
    cont_arr = valid["continuation"].to_numpy()
    n_total = len(valid)
    null_rates = np.empty(N_PERM)
    for i in range(N_PERM):
        idx = rng.choice(n_total, size=n, replace=False)
        null_rates[i] = cont_arr[idx].mean()
    null_mean = float(null_rates.mean())
    extremity = np.abs(null_rates - null_mean)
    obs_extremity = abs(observed_rate - null_mean)
    p_value = (1 + np.sum(extremity >= obs_extremity)) / (N_PERM + 1)

    return {
        "k": k, "n_trigger_days": n, "n_continuation": k_cont,
        "observed_continuation_rate": observed_rate, "ci_95": list(ci),
        "baseline_continuation_rate_nontrigger_days": baseline_rate,
        "permutation_null_mean": null_mean,
        "absolute_lift_vs_permutation_null": observed_rate - null_mean,
        "absolute_lift_vs_nontrigger_baseline": observed_rate - baseline_rate,
        "p_value_raw": float(p_value),
        "direction": "continuation_favored" if observed_rate > 0.5 else "reversal_favored",
    }


def main() -> int:
    daily = build_daily_series()
    print(f"Discovery daily series: {len(daily)} trading dates")

    rng = np.random.default_rng(RNG_SEED)
    results = [test_threshold(daily, k, rng) for k in THRESHOLDS]

    p_values = [r["p_value_raw"] for r in results if "p_value_raw" in r]
    bonf = bonferroni(p_values)
    bh = benjamini_hochberg(p_values)
    j = 0
    for r in results:
        if "p_value_raw" in r:
            r["survives_bonferroni"] = bool(bonf[j])
            r["survives_bh"] = bool(bh[j])
            j += 1

    print("\n=== H013: vol-shock -> next-day continuation, all 3 pre-declared thresholds ===")
    for r in results:
        if "p_value_raw" not in r:
            print(r)
            continue
        print(f"K={r['k']}: n={r['n_trigger_days']}, observed={r['observed_continuation_rate']:.3f}, "
              f"CI={r['ci_95']}, baseline(nontrigger)={r['baseline_continuation_rate_nontrigger_days']:.3f}, "
              f"perm_null={r['permutation_null_mean']:.3f}, lift={r['absolute_lift_vs_permutation_null']:+.3f}, "
              f"p={r['p_value_raw']:.4f}, direction={r['direction']}, "
              f"bonf={'Y' if r['survives_bonferroni'] else 'N'}, bh={'Y' if r['survives_bh'] else 'N'}")

    any_survives = any(r.get("survives_bonferroni") or r.get("survives_bh") for r in results)

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "discovery_range": [str(DISCOVERY_START), str(DISCOVERY_END)],
        "n_permutations": N_PERM, "rng_seed": RNG_SEED,
        "results": results,
        "any_threshold_survives_correction": any_survives,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"\nAny threshold survives correction: {any_survives}")
    print(f"Written to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
