"""Phase 55 (timing) + Phase 58 (day-of-week), DISCOVERY only.

Phase 55: for H003/H004/H011/H012 (the break hypotheses), when within the
current session does the break happen? Bucketed by minutes-since-session-
open, using the blueprint's own bucket edges (0-5/5-15/15-30/30-60/
60-120/120-240 min).

Phase 58: touch/break rates for the strong group, split by weekday.
Descriptive only -- no new baseline/significance machinery beyond what
Phase 54/64 already established; this is about characterizing shape, not
introducing another correction-tested hypothesis.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.research.context_features import build_daily_context, join_context  # noqa: E402
from src.research.data_split import discovery_slice  # noqa: E402

LABELS_PATH = Path("data/raw/es_futures/session_labels.parquet")
GEOMETRY_PATH = Path("data/raw/es_futures/session_geometry.parquet")
OUT_PATH = Path("data/raw/es_futures/phase55_58_results.json")

TIME_BUCKETS = [(0, 5), (5, 15), (15, 30), (30, 60), (60, 120), (120, 240), (240, 99999)]
BREAK_HYPS = [
    ("H003", "europe_vs_asia", "europe", "break_high_time", "broke_high"),
    ("H004", "europe_vs_asia", "europe", "break_low_time", "broke_low"),
    ("H011", "ny_vs_europe", "new_york", "break_high_time", "broke_high"),
    ("H012", "ny_vs_europe", "new_york", "break_low_time", "broke_low"),
]
STRONG_HYPS = [
    ("H001", "europe_vs_asia", "touched_high"), ("H002", "europe_vs_asia", "touched_low"),
    ("H003", "europe_vs_asia", "broke_high"), ("H004", "europe_vs_asia", "broke_low"),
    ("H009", "ny_vs_europe", "touched_high"), ("H010", "ny_vs_europe", "touched_low"),
    ("H011", "ny_vs_europe", "broke_high"), ("H012", "ny_vs_europe", "broke_low"),
]


def bucket_label(mins: float) -> str:
    for lo, hi in TIME_BUCKETS:
        if lo <= mins < hi:
            return f"{lo}-{hi if hi < 99999 else '240+'}min"
    return "unknown"


def main() -> int:
    labels = pd.read_parquet(LABELS_PATH)
    disc = discovery_slice(labels)
    context = build_daily_context()
    disc = join_context(disc, context)

    geo = pd.read_parquet(GEOMETRY_PATH)
    geo["trading_date"] = pd.to_datetime(geo["trading_date"]).dt.date
    geo_open = geo.set_index(["trading_date", "session"])["utc_open"]

    results = {"timing": {}, "day_of_week": {}}

    # --- Phase 55: timing ---
    for hyp_id, comparison, session_name, time_col, break_col in BREAK_HYPS:
        sub = disc[(disc["comparison"] == comparison) & (disc[break_col])].copy()
        opens = sub.apply(lambda r: geo_open.get((r["trading_date"], session_name)), axis=1)
        mins_since_open = (pd.to_datetime(sub[time_col]) - pd.to_datetime(opens)).dt.total_seconds() / 60
        buckets = mins_since_open.apply(bucket_label)
        counts = buckets.value_counts().to_dict()
        results["timing"][hyp_id] = {"n_breaks": len(sub), "bucket_counts": counts}
        print(f"{hyp_id} timing (n={len(sub)}): {counts}")

    # --- Phase 58: day of week ---
    for hyp_id, comparison, col in STRONG_HYPS:
        sub = disc[disc["comparison"] == comparison]
        by_dow = sub.groupby("weekday")[col].agg(["mean", "count"])
        by_dow = by_dow.reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        results["day_of_week"][hyp_id] = by_dow.to_dict(orient="index")
        print(f"{hyp_id} by weekday: " + " ".join(f"{d}:{r['mean']:.2f}(n={int(r['count'])})" for d, r in by_dow.iterrows()))

    with open(OUT_PATH, "w") as f:
        json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "results": results}, f, indent=2, default=str)
    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
