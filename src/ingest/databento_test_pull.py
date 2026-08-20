"""Phase 46 smoke test: pull a small Databento sample and sanity-check it.

Deliberately tiny in scope -- one contract, one month, 1-minute bars --
so we can confirm credentials, cost, and data shape all look right
before ever requesting anything larger. Prints the estimated cost via
metadata.get_cost() and aborts before streaming if it looks off.

Front-month symbol is hardcoded rather than derived from
``calendar.roll``, because that module's roll-date logic is not yet
validated against real volume data (see roll.py's module docstring --
that validation is blocked on this exact ingestion landing). As of
2026-08-15, the CME-quarterly front month is the September 2026
contract: ``ESU26`` in this project's internal notation
(calendar/contracts.py), which is Databento's raw_symbol ``ESU6`` on
GLBX.MDP3.
"""

from __future__ import annotations

import os
import sys

import databento as db

DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"
SYMBOL = "ESU6"  # front-month ES, GLBX.MDP3 raw_symbol convention
START = "2026-07-01"
END = "2026-08-01"  # exclusive
OUT_PATH = "data/raw/es_ohlcv1m_ESU6_202607.parquet"

# A cost above this aborts the pull rather than silently spending money.
COST_CEILING_USD = 5.00


def main() -> int:
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        print("DATABENTO_API_KEY is not set in the environment.", file=sys.stderr)
        return 1

    client = db.Historical(api_key)

    print(f"Requesting cost estimate: {DATASET} {SCHEMA} {SYMBOL} {START} -> {END}")
    estimated_cost = client.metadata.get_cost(
        dataset=DATASET,
        symbols=SYMBOL,
        schema=SCHEMA,
        start=START,
        end=END,
        stype_in="raw_symbol",
    )
    print(f"Estimated cost: ${estimated_cost:.4f} USD")

    if estimated_cost > COST_CEILING_USD:
        print(
            f"Estimated cost exceeds ceiling (${COST_CEILING_USD:.2f}); aborting "
            "without pulling data.",
            file=sys.stderr,
        )
        return 1

    print("Pulling data...")
    store = client.timeseries.get_range(
        dataset=DATASET,
        symbols=SYMBOL,
        schema=SCHEMA,
        start=START,
        end=END,
        stype_in="raw_symbol",
    )
    df = store.to_df()

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_parquet(OUT_PATH)
    print(f"Saved {len(df)} rows to {OUT_PATH}")

    print(f"\nRow count: {len(df)}")
    print("\nFirst rows:")
    print(df.head())
    print("\nLast rows:")
    print(df.tail())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
