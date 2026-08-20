"""Canonical ES bar schema and source-agnostic normalization (blueprint Phase 46).

No actual ES historical data has been acquired yet -- per
docs/blueprint.md, that's still the project's immediate blocker ("Do not
download anything yet. Choose the exact data route."). This module does
NOT wire up any real or fake data source. It defines the canonical
schema real data will be normalized into once a source is chosen, and a
source-agnostic normalization function, so the validation layer
(validate.py) and everything downstream (session geometry, and
eventually the hypothesis layer) has a stable contract to target the
moment real data arrives.

Deliberately generic about the source: at this point we don't know
whether the eventual data will come as CSV, Parquet, or an API response,
so `normalize_to_canonical_schema` takes an already-loaded DataFrame plus
a column mapping, rather than assuming a specific file format or vendor
column-naming convention.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.calendar.timestamps import to_utc_timestamp

CANONICAL_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "contract_symbol",
)


@dataclass(frozen=True)
class ColumnMapping:
    """Maps a raw source DataFrame's column names to the canonical schema."""

    timestamp: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    contract_symbol: str


def normalize_to_canonical_schema(
    raw: pd.DataFrame,
    mapping: ColumnMapping,
    source_tz: str | None = None,
) -> pd.DataFrame:
    """Normalize a raw bar DataFrame (any source) into the canonical schema.

    `source_tz` is passed through to `to_utc_timestamp` for naive raw
    timestamps -- see that function's docstring: naive timestamps with no
    `source_tz` raise rather than being silently assumed to be UTC.

    Does not validate bar content (impossible prices, duplicates, gaps,
    etc.) -- that's validate.py's job, run separately after this.
    """
    missing = [f for f in mapping.__dataclass_fields__ if getattr(mapping, f) not in raw.columns]
    if missing:
        raise ValueError(f"raw DataFrame is missing mapped source column(s): {missing}")

    normalized_timestamps = [
        to_utc_timestamp(ts, source_tz=source_tz) for ts in raw[mapping.timestamp]
    ]

    return pd.DataFrame(
        {
            "timestamp": pd.DatetimeIndex(normalized_timestamps),
            "open": raw[mapping.open].astype(float).to_numpy(),
            "high": raw[mapping.high].astype(float).to_numpy(),
            "low": raw[mapping.low].astype(float).to_numpy(),
            "close": raw[mapping.close].astype(float).to_numpy(),
            "volume": raw[mapping.volume].astype(float).to_numpy(),
            "contract_symbol": raw[mapping.contract_symbol].astype(str).to_numpy(),
        }
    )
