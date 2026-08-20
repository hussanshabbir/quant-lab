"""Phase 57 (prior-session/trend conditioning) + Phase 64 (historical
stability), applied specifically to H005-H008 -- direct answer to the
bull-market-trend confound flagged in the Phase 54 report.

Two cuts, both on DISCOVERY data only:
  1. Split by TREND REGIME (trailing 60-trading-day return sign, up/down).
     If the accept/reject asymmetry is just the secular 2010-2021 uptrend
     showing up in the acceptance/rejection labels, it should FLIP sign
     (or at least shrink toward 0) in down-trend periods, since a
     mechanical trend-following artifact reverses with the trend. If it
     holds the SAME direction and magnitude in both regimes, that's
     evidence of a real, trend-independent structural effect.
  2. Split by YEAR. If the effect is driven by a handful of unusual years
     rather than being broadly present, that's also grounds to distrust it
     as a real, general effect.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.research.context_features import build_daily_context, join_context  # noqa: E402
from src.research.data_split import discovery_slice  # noqa: E402

LABELS_PATH = Path("data/raw/es_futures/session_labels.parquet")
OUT_PATH = Path("data/raw/es_futures/phase57_64_h005_h008_results.json")

HYPS = [
    ("H005", "broke_high", "broke_high_accepted", "Break Asia high -> acceptance"),
    ("H006", "broke_high", "broke_high_rejected", "Break Asia high -> rejection"),
    ("H007", "broke_low", "broke_low_accepted", "Break Asia low -> acceptance"),
    ("H008", "broke_low", "broke_low_rejected", "Break Asia low -> rejection"),
]


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    from scipy.stats import norm
    if n == 0:
        return (float("nan"), float("nan"))
    z = norm.ppf(1 - alpha / 2)
    p = k / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return ((center - half) / denom, (center + half) / denom)


def rate_and_test(df: pd.DataFrame, break_col: str, outcome_col: str) -> dict:
    from scipy.stats import binomtest
    broke = df[df[break_col]]
    n = len(broke)
    if n == 0:
        return {"n": 0, "rate": None, "ci_95": [None, None], "p_value_vs_half": None}
    k = int(broke[outcome_col].sum())
    rate = k / n
    ci = wilson_ci(k, n)
    p = binomtest(k, n, p=0.5, alternative="two-sided").pvalue if n > 0 else None
    return {"n": n, "k": k, "rate": rate, "ci_95": list(ci), "p_value_vs_half": float(p) if p is not None else None}


def main() -> int:
    labels = pd.read_parquet(LABELS_PATH)
    disc = discovery_slice(labels)
    disc = disc[disc["comparison"] == "europe_vs_asia"]

    context = build_daily_context()
    disc = join_context(disc, context)

    print(f"H005-H008 discovery rows (europe_vs_asia): {len(disc)}")
    print(f"Trend regime split: {disc['trend_regime'].value_counts().to_dict()}")

    results = {"by_trend_regime": {}, "by_year": {}, "overall": {}}

    for hyp_id, break_col, outcome_col, desc in HYPS:
        results["overall"][hyp_id] = {"description": desc, **rate_and_test(disc, break_col, outcome_col)}

        by_trend = {}
        for regime in ["up", "down"]:
            sub = disc[disc["trend_regime"] == regime]
            by_trend[regime] = rate_and_test(sub, break_col, outcome_col)
        results["by_trend_regime"][hyp_id] = {"description": desc, **by_trend}

        by_year = {}
        for year in sorted(disc["year"].dropna().unique()):
            sub = disc[disc["year"] == year]
            by_year[int(year)] = rate_and_test(sub, break_col, outcome_col)
        results["by_year"][hyp_id] = {"description": desc, **by_year}

    with open(OUT_PATH, "w") as f:
        json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "results": results}, f, indent=2, default=str)

    print("\n=== OVERALL (discovery, unconditional) ===")
    for hyp_id, r in results["overall"].items():
        print(f"{hyp_id}: n={r['n']}, rate={r['rate']:.3f}, CI={r['ci_95']}, p_vs_0.5={r['p_value_vs_half']:.4f}")

    print("\n=== BY TREND REGIME ===")
    for hyp_id, r in results["by_trend_regime"].items():
        up, down = r["up"], r["down"]
        print(f"{hyp_id} ({r['description']}):")
        print(f"  UP   trend: n={up['n']}, rate={up['rate']:.3f}, CI={up['ci_95']}, p={up['p_value_vs_half']:.4f}")
        print(f"  DOWN trend: n={down['n']}, rate={down['rate']:.3f}, CI={down['ci_95']}, p={down['p_value_vs_half']:.4f}")

    print("\n=== BY YEAR ===")
    for hyp_id, r in results["by_year"].items():
        print(f"{hyp_id}:")
        for year, stats in r.items():
            if year == "description":
                continue
            if stats["n"] == 0:
                continue
            print(f"  {year}: n={stats['n']}, rate={stats['rate']:.3f}, p={stats['p_value_vs_half']:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
