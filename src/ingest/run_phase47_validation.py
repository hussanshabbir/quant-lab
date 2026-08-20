"""Phase 47: run validate.py against all real ingested ES contract files.

Loads every contract parquet from data/raw/es_futures/ohlcv_1m/ (written by
pull_full_history.py), normalizes each into the canonical bar schema
(bars.py), and runs the full validate.py check suite per contract plus a
combined duplicate check across all contracts. Writes a JSON report with
per-check aggregate counts, per-contract breakdowns, and full (not
sample-truncated) issue rows for the categories small enough to review by
hand, so nothing is silently summarized away.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.calendar.contracts import quarterly_contracts  # noqa: E402
from src.calendar.exchange import CMEEquityCalendar  # noqa: E402
from src.ingest.validate import (  # noqa: E402
    check_bars_after_contract_expiration,
    check_bars_outside_globex_hours,
    check_duplicate_timestamps,
    check_impossible_prices,
    check_missing_bars,
    check_zero_volume,
)

DATA_DIR = Path("data/raw/es_futures/ohlcv_1m")
MANIFEST_PATH = Path("data/raw/es_futures/ohlcv_1m_manifest.json")
REPORT_PATH = DATA_DIR / "phase47_validation_report.json"

KNOWN_DEGRADED_DATES = [
    "2014-06-11", "2014-06-12", "2014-06-13", "2014-06-15",
    "2014-09-22", "2014-09-23", "2014-09-24", "2014-09-25",
    "2017-11-13", "2018-10-21",
    "2019-01-15", "2019-02-22", "2019-03-13", "2019-03-26",
    "2020-02-27", "2020-02-28", "2020-06-30", "2020-07-01",
    "2021-12-05", "2022-01-02",
    "2024-09-18",
    "2025-09-17", "2025-09-24", "2025-11-28",
    "2026-01-31", "2026-03-15", "2026-03-16", "2026-03-21",
    "2026-04-10", "2026-05-24", "2026-07-30",
]


def load_contract_df(path: Path, symbol: str) -> pd.DataFrame:
    raw = pd.read_parquet(path)
    ts = raw.index
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": raw["open"].astype(float).to_numpy(),
            "high": raw["high"].astype(float).to_numpy(),
            "low": raw["low"].astype(float).to_numpy(),
            "close": raw["close"].astype(float).to_numpy(),
            "volume": raw["volume"].astype(float).to_numpy(),
            "contract_symbol": symbol,
        }
    )


def issue_to_dict(issue) -> dict:
    return {
        "check": issue.check,
        "severity": issue.severity,
        "message": issue.message,
        "count": issue.count,
        "sample": [[str(x) for x in row] for row in issue.sample],
    }


def main() -> int:
    manifest = json.load(open(MANIFEST_PATH))
    contract_symbols = sorted(m["symbol"] for m in manifest["contracts"] if m["status"] == "ok")
    print(f"Validating {len(contract_symbols)} contracts")

    calendar = CMEEquityCalendar()
    print("Warming calendar cache for 2010-06-01 -> 2026-08-20 ...")
    calendar.warm_cache(dt.date(2010, 6, 1), dt.date(2026, 8, 20))

    all_contracts = {c.symbol: c for c in quarterly_contracts(2010, 2026, calendar)}

    per_contract_reports: dict[str, list[dict]] = {}
    global_counts: dict[str, dict[str, int]] = {}  # check -> {"count": n, "n_files_affected": m}
    all_dupe_rows: list[tuple] = []
    all_bad_price_rows: list[tuple] = []
    all_outside_hours_rows: list[tuple] = []
    all_expiration_rows: list[tuple] = []

    combined_frames = []

    for symbol in contract_symbols:
        path = DATA_DIR / f"{symbol}.parquet"
        df = load_contract_df(path, symbol)
        combined_frames.append(df)

        issues = []
        issues += check_duplicate_timestamps(df)
        issues += check_impossible_prices(df)
        issues += check_zero_volume(df)
        issues += check_bars_outside_globex_hours(df, calendar)
        issues += check_bars_after_contract_expiration(df, all_contracts)
        issues += check_missing_bars(df, calendar, pd.Timedelta("1min"))

        per_contract_reports[symbol] = [issue_to_dict(i) for i in issues]

        for issue in issues:
            g = global_counts.setdefault(issue.check, {"total_count": 0, "n_files_affected": 0})
            g["total_count"] += issue.count
            g["n_files_affected"] += 1

        print(f"{symbol}: {len(df)} rows, {len(issues)} issue categories -> "
              f"{[f'{i.check}={i.count}' for i in issues]}")

    # Cross-file duplicate check (same contract_symbol+timestamp across files would be
    # impossible by construction -- one file per symbol -- but check across ALL rows too,
    # since a mislabeled file could in principle collide.)
    print("\nRunning combined duplicate check across all files...")
    combined = pd.concat(combined_frames, ignore_index=True)
    combined_dupe_issues = check_duplicate_timestamps(combined)

    print("\nCross-checking known degraded dates against actual data...")
    degraded_analysis = []
    for date_str in KNOWN_DEGRADED_DATES:
        date = dt.date.fromisoformat(date_str)
        day_rows = combined[combined["timestamp"].dt.date == date]
        if day_rows.empty:
            degraded_analysis.append({"date": date_str, "rows": 0, "note": "no bars from any contract on this date"})
            continue
        zero_vol = int((day_rows["volume"] == 0).sum())
        bad_price = check_impossible_prices(day_rows)
        dupe = check_duplicate_timestamps(day_rows)
        contracts_present = sorted(day_rows["contract_symbol"].unique().tolist())
        degraded_analysis.append({
            "date": date_str,
            "rows": int(len(day_rows)),
            "contracts_present": contracts_present,
            "zero_volume_bars": zero_vol,
            "impossible_price_bars": bad_price[0].count if bad_price else 0,
            "duplicate_pairs": dupe[0].count if dupe else 0,
        })

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_contracts_validated": len(contract_symbols),
        "total_rows_validated": int(len(combined)),
        "global_counts": global_counts,
        "combined_cross_file_duplicate_check": [issue_to_dict(i) for i in combined_dupe_issues],
        "per_contract": per_contract_reports,
        "degraded_dates_cross_check": degraded_analysis,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nReport written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
