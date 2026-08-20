"""Phase 46: full historical pull of individual ES quarterly futures contracts.

Pulls ohlcv-1m for every ES outright quarterly contract (H/M/U/Z) from
GLBX.MDP3's dataset start (2010-06-06) through today, and writes one
parquet file per contract under ``data/raw/es_futures/ohlcv_1m/`` so
Phase 47 (validation) and Phase 48 (roll-date determination) can each
iterate the directory contract-by-contract without re-parsing a giant
combined file.

Deliberately pulls each contract's *entire* listed life (not just its
front-month window) -- see calendar/roll.py's module docstring: the
roll date is determined from real volume/OI, which requires having the
overlapping tail/head of adjacent contracts on disk, not a
pre-spliced continuous series.

Symbol-collision note: Databento's GLBX.MDP3 raw_symbol convention uses
a single-digit year (e.g. "ESU6"), which repeats every 10 years. Each
request below is scoped to one specific contract's own trading window
(computed from calendar/contracts.py's real last-trade-date logic, not
a guess), so no single request's date range is ever wide enough to
span two different contracts sharing the same raw symbol.

Cost ceiling: this run was pre-approved by the user against a quoted
total of ~$24.84 (two decade-scoped batch estimates: 2010-2019 outrights
$13.03, 2020-2026 outrights $11.80). The ceiling below is raised well
above that quote for this one run, per that approval -- it still exists
as a safety net against a materially different number appearing at
execution time, not as a normal day-to-day limit.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import databento as db
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.calendar.contracts import quarterly_contracts  # noqa: E402
from src.calendar.exchange import CMEEquityCalendar  # noqa: E402

DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"
DATASET_START = dt.date(2010, 6, 6)
OUT_DIR = Path("data/raw/es_futures/ohlcv_1m")
MANIFEST_PATH = Path("data/raw/es_futures/ohlcv_1m_manifest.json")

# Pre-approved for this run only (quoted total ~$24.84); not a standing default.
COST_CEILING_USD = 35.00

# How far back from a contract's own last-trade date to request. CME lists ES
# quarterlies well under 3 years out; padding generously here is harmless --
# Databento just returns whatever real data exists in the window, and 3 years
# is nowhere near the 10-year raw-symbol reuse boundary.
LOOKBACK_DAYS = 3 * 365

MAX_RETRIES = 3


def contract_window(last_trade_date: dt.date, today: dt.date) -> tuple[dt.date, dt.date] | None:
    """(start, end) to request for one contract, or None if it has zero overlap
    with the dataset (i.e. it expired before the dataset even starts)."""
    if last_trade_date < DATASET_START:
        return None
    start = max(DATASET_START, last_trade_date - dt.timedelta(days=LOOKBACK_DAYS))
    if last_trade_date < today:
        end = last_trade_date + dt.timedelta(days=1)  # exclusive end, include full last day
    else:
        # Contract is still active: don't request past "now" -- Databento's
        # historical API rejects an end time in the future (real-time
        # licensing boundary), even though `today` itself is fine.
        end = today
    return start, end


def pull_one(client: db.Historical, raw_symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            store = client.timeseries.get_range(
                dataset=DATASET,
                symbols=raw_symbol,
                schema=SCHEMA,
                start=start.isoformat(),
                end=end.isoformat(),
                stype_in="raw_symbol",
            )
            return store.to_df()
        except db.common.error.BentoError as exc:
            last_exc = exc
            print(f"  attempt {attempt}/{MAX_RETRIES} failed for {raw_symbol}: {exc}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(5 * attempt)
    assert last_exc is not None
    raise last_exc


def main() -> int:
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        print("DATABENTO_API_KEY is not set in the environment.", file=sys.stderr)
        return 1

    client = db.Historical(api_key)
    calendar = CMEEquityCalendar()
    today = dt.date.today()

    contracts = quarterly_contracts(2010, today.year, calendar)

    # Two decade-scoped batches, matching what was already quoted and approved.
    batch_a_symbols = [f"ES{'HMUZ'[m // 3 - 1]}{y % 10}" for y in range(2010, 2020) for m in (3, 6, 9, 12)]
    batch_b_symbols = [f"ES{'HMUZ'[m // 3 - 1]}{y % 10}" for y in range(2020, 2027) for m in (3, 6, 9, 12)]

    cost_a = client.metadata.get_cost(
        dataset=DATASET, symbols=batch_a_symbols, schema=SCHEMA,
        start="2010-06-06", end="2020-01-01", stype_in="raw_symbol",
    )
    cost_b = client.metadata.get_cost(
        dataset=DATASET, symbols=batch_b_symbols, schema=SCHEMA,
        start="2020-01-01", end=today.isoformat(), stype_in="raw_symbol",
    )
    total_cost = cost_a + cost_b
    print(f"Re-verified cost immediately before pulling: batch A ${cost_a:.4f} + batch B ${cost_b:.4f} = ${total_cost:.4f}")

    if total_cost > COST_CEILING_USD:
        print(
            f"Cost ${total_cost:.4f} exceeds pre-approved ceiling ${COST_CEILING_USD:.2f}; aborting.",
            file=sys.stderr,
        )
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    skipped: list[dict] = []

    for contract in contracts:
        window = contract_window(contract.last_trade_date, today)
        if window is None:
            skipped.append({
                "symbol": contract.symbol,
                "reason": f"last_trade_date {contract.last_trade_date} predates dataset start {DATASET_START}",
            })
            print(f"Skipping {contract.symbol}: {skipped[-1]['reason']}")
            continue

        start, end = window
        year_digit = contract.contract_year % 10
        month_code = {3: "H", 6: "M", 9: "U", 12: "Z"}[contract.contract_month]
        raw_symbol = f"ES{month_code}{year_digit}"

        print(f"Pulling {contract.symbol} (raw={raw_symbol}) {start} -> {end}")
        try:
            df = pull_one(client, raw_symbol, start, end)
        except db.common.error.BentoError as exc:
            manifest.append({
                "symbol": contract.symbol,
                "raw_symbol": raw_symbol,
                "requested_start": start.isoformat(),
                "requested_end": end.isoformat(),
                "last_trade_date": contract.last_trade_date.isoformat(),
                "status": "FAILED",
                "error": str(exc),
                "row_count": 0,
            })
            print(f"  FAILED: {exc}", file=sys.stderr)
            continue

        out_path = OUT_DIR / f"{contract.symbol}.parquet"
        df.to_parquet(out_path)

        manifest.append({
            "symbol": contract.symbol,
            "raw_symbol": raw_symbol,
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "last_trade_date": contract.last_trade_date.isoformat(),
            "status": "ok",
            "row_count": len(df),
            "first_ts": str(df.index.min()) if len(df) else None,
            "last_ts": str(df.index.max()) if len(df) else None,
            "file": str(out_path),
        })
        print(f"  {len(df)} rows -> {out_path}")

    with open(MANIFEST_PATH, "w") as f:
        json.dump(
            {
                "pulled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "quoted_cost_usd": total_cost,
                "batch_a_cost_usd": cost_a,
                "batch_b_cost_usd": cost_b,
                "contracts": manifest,
                "skipped": skipped,
            },
            f,
            indent=2,
            default=str,
        )

    total_rows = sum(m["row_count"] for m in manifest)
    failures = [m for m in manifest if m["status"] != "ok"]

    print("\n=== SUMMARY ===")
    print(f"Total actual cost (quoted immediately pre-pull): ${total_cost:.4f}")
    print(f"Contracts attempted: {len(manifest)}  |  skipped (no dataset overlap): {len(skipped)}")
    print(f"Total rows: {total_rows}")
    print(f"Failures: {len(failures)}")
    for f_ in failures:
        print(f"  FAILED {f_['symbol']}: {f_.get('error')}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
