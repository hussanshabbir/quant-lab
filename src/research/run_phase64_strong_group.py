"""Phase 64: historical stability of the strong group (H001-H004, H009-H012)
across years and volatility regimes (Phase 56). DISCOVERY data only.

For each year and each volatility quintile, recomputes both the observed
rate AND a slice-local baseline (same local block-permutation method as
Phase 54, restricted to that slice's own rows) -- not just the observed
rate alone, so "stability" means the LIFT over a matched null holds up,
not just that the raw rate stays high (which could just track how
volatility itself varies by year).
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
from src.research.run_phase54_hypotheses import permutation_baseline, wilson_ci  # noqa: E402

LABELS_PATH = Path("data/raw/es_futures/session_labels.parquet")
OUT_PATH = Path("data/raw/es_futures/phase64_strong_group_results.json")

N_PERM_SLICE = 300  # reduced from Phase 54's 2000 -- many more slices here
RNG_SEED = 7

HYPS = [
    ("H001", "europe_vs_asia", "touched_high"), ("H002", "europe_vs_asia", "touched_low"),
    ("H003", "europe_vs_asia", "broke_high"), ("H004", "europe_vs_asia", "broke_low"),
    ("H009", "ny_vs_europe", "touched_high"), ("H010", "ny_vs_europe", "touched_low"),
    ("H011", "ny_vs_europe", "broke_high"), ("H012", "ny_vs_europe", "broke_low"),
]


def slice_stats(sub: pd.DataFrame, col: str, rng: np.random.Generator) -> dict:
    n = len(sub)
    if n < 15:  # too few rows for a meaningful local-block null
        return {"n": n, "rate": None, "baseline": None, "lift": None}
    k = int(sub[col].sum())
    observed = k / n
    ci = wilson_ci(k, n)
    null_rates = permutation_baseline(sub, col, N_PERM_SLICE, rng)
    baseline = float(null_rates.mean())
    lift = observed - baseline
    return {"n": n, "k": k, "rate": observed, "ci_95": list(ci), "baseline": baseline, "lift": lift}


def main() -> int:
    labels = pd.read_parquet(LABELS_PATH)
    disc = discovery_slice(labels)
    context = build_daily_context()
    disc = join_context(disc, context)

    rng = np.random.default_rng(RNG_SEED)
    results = {"by_year": {}, "by_vol_quintile": {}}

    for hyp_id, comparison, col in HYPS:
        comp_df = disc[disc["comparison"] == comparison]

        by_year = {}
        for year in sorted(comp_df["year"].dropna().unique()):
            sub = comp_df[comp_df["year"] == year]
            by_year[int(year)] = slice_stats(sub, col, rng)
        results["by_year"][hyp_id] = by_year
        print(f"{hyp_id} by year done")

        by_vol = {}
        for q in [1, 2, 3, 4, 5]:
            sub = comp_df[comp_df["vol_quintile"] == q]
            by_vol[q] = slice_stats(sub, col, rng)
        results["by_vol_quintile"][hyp_id] = by_vol
        print(f"{hyp_id} by vol quintile done")

    with open(OUT_PATH, "w") as f:
        json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "results": results}, f, indent=2, default=str)

    print("\n=== BY YEAR: lift (observed - local baseline) ===")
    for hyp_id in results["by_year"]:
        row = []
        for year, s in results["by_year"][hyp_id].items():
            if s["lift"] is None:
                continue
            row.append(f"{year}:{s['lift']:+.2f}")
        print(f"{hyp_id}: " + " ".join(row))

    print("\n=== BY VOLATILITY QUINTILE (1=lowest, 5=highest): lift ===")
    for hyp_id in results["by_vol_quintile"]:
        row = []
        for q, s in results["by_vol_quintile"][hyp_id].items():
            if s["lift"] is None:
                continue
            row.append(f"Q{q}:{s['lift']:+.2f}(n={s['n']})")
        print(f"{hyp_id}: " + " ".join(row))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
