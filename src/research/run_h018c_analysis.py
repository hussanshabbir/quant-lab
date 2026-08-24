"""H018c analysis: cost-inclusive P&L on the real historical straddle
events collected by run_h018c_options_structure.py. Same design as
pre-registered -- 4 variants (threshold in {1.5, 2.0} x horizon in {5, 10}),
Bonferroni + BH, trigger vs matched-random baseline.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, ttest_ind

OUT_DIR = Path("data/raw/vix")
ROUND_TRIP_COST_PER_LEG = 0.04
ALPHA = 0.05


def pnl(event: dict, horizon: int) -> float | None:
    if horizon == 5:
        call_exit, put_exit = event.get("call_5d"), event.get("put_5d")
    else:
        call_exit, put_exit = event.get("call_10d"), event.get("put_10d")
    if call_exit is None or put_exit is None:
        return None
    entry_cost = event["call_entry"] * (1 + ROUND_TRIP_COST_PER_LEG / 2) + event["put_entry"] * (1 + ROUND_TRIP_COST_PER_LEG / 2)
    exit_proceeds = call_exit * (1 - ROUND_TRIP_COST_PER_LEG / 2) + put_exit * (1 - ROUND_TRIP_COST_PER_LEG / 2)
    return (exit_proceeds - entry_cost) / entry_cost


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
    trigger_events = json.load(open(OUT_DIR / "h018c_trigger_events.json"))
    baseline_events = json.load(open(OUT_DIR / "h018c_baseline_events.json"))

    results = []
    for threshold in [1.5, 2.0]:
        if threshold == 1.5:
            trig_subset = trigger_events
        else:
            trig_subset = [e for e in trigger_events if e.get("is_2x")]

        for horizon in [5, 10]:
            trig_pnls = [pnl(e, horizon) for e in trig_subset]
            trig_pnls = [p for p in trig_pnls if p is not None]
            base_pnls = [pnl(e, horizon) for e in baseline_events]
            base_pnls = [p for p in base_pnls if p is not None]

            n_trig, n_base = len(trig_pnls), len(base_pnls)
            if n_trig < 10 or n_base < 10:
                results.append({"threshold": threshold, "horizon": horizon, "note": "too few events"})
                continue

            trig_arr, base_arr = np.array(trig_pnls), np.array(base_pnls)
            mean_trig, mean_base = trig_arr.mean(), base_arr.mean()
            win_rate_trig = (trig_arr > 0).mean()
            win_rate_base = (base_arr > 0).mean()

            t_result = ttest_ind(trig_arr, base_arr, equal_var=False)
            u_result = mannwhitneyu(trig_arr, base_arr, alternative="two-sided")

            se_diff = np.sqrt(trig_arr.var(ddof=1) / n_trig + base_arr.var(ddof=1) / n_base)
            diff = mean_trig - mean_base
            ci = (diff - 1.96 * se_diff, diff + 1.96 * se_diff)

            results.append({
                "threshold": threshold, "horizon": horizon,
                "n_trigger": n_trig, "n_baseline": n_base,
                "mean_return_trigger_pct": float(mean_trig * 100),
                "mean_return_baseline_pct": float(mean_base * 100),
                "win_rate_trigger": float(win_rate_trig),
                "win_rate_baseline": float(win_rate_base),
                "diff_pct": float(diff * 100),
                "diff_ci95_pct": [float(ci[0] * 100), float(ci[1] * 100)],
                "p_value_ttest": float(t_result.pvalue),
                "p_value_mannwhitney": float(u_result.pvalue),
                "trigger_pnls_pct": [float(p * 100) for p in trig_pnls],
            })

    p_values = [r["p_value_ttest"] for r in results if "p_value_ttest" in r]
    bonf = bonferroni(p_values)
    bhr = bh(p_values)
    j = 0
    for r in results:
        if "p_value_ttest" in r:
            r["survives_bonferroni"] = bool(bonf[j])
            r["survives_bh"] = bool(bhr[j])
            j += 1

    with open(OUT_DIR / "h018c_final_results.json", "w") as f:
        json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "cost_model": {"round_trip_cost_per_leg_pct": ROUND_TRIP_COST_PER_LEG * 100},
                    "results": results}, f, indent=2, default=str)

    print("\n=== H018c FINAL RESULTS (cost-inclusive straddle P&L) ===")
    for r in results:
        if "note" in r:
            print(r)
            continue
        print(f"\nthreshold={r['threshold']}x, horizon={r['horizon']}d:")
        print(f"  n_trigger={r['n_trigger']}, n_baseline={r['n_baseline']}")
        print(f"  mean return: trigger={r['mean_return_trigger_pct']:+.2f}%, baseline={r['mean_return_baseline_pct']:+.2f}%")
        print(f"  win rate: trigger={r['win_rate_trigger']:.1%}, baseline={r['win_rate_baseline']:.1%}")
        print(f"  diff={r['diff_pct']:+.2f}% CI=[{r['diff_ci95_pct'][0]:+.2f}%,{r['diff_ci95_pct'][1]:+.2f}%]")
        print(f"  p(t-test)={r['p_value_ttest']:.4f}, p(Mann-Whitney)={r['p_value_mannwhitney']:.4f}")
        print(f"  bonf={'Y' if r['survives_bonferroni'] else 'N'}, bh={'Y' if r['survives_bh'] else 'N'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
