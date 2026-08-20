"""Tests for src.ingest.bars.normalize_to_canonical_schema.

All input DataFrames here are synthetic fixtures with clearly
vendor-arbitrary column names, used only to prove the normalization
logic works -- not real vendor data.
"""

import pandas as pd
import pytest

from src.ingest.bars import CANONICAL_COLUMNS, ColumnMapping, normalize_to_canonical_schema


def _raw_vendor_df() -> pd.DataFrame:
    """Synthetic fixture mimicking an arbitrary vendor's column naming
    (e.g. "Time", "O", "H", "L", "C", "Vol", "Symbol") and a naive
    local-time timestamp, to prove normalization handles both renaming
    and timezone localization."""
    return pd.DataFrame(
        {
            "Time": ["2026-01-15 09:30:00", "2026-01-15 09:31:00"],
            "O": [100.0, 101.0],
            "H": [101.5, 102.0],
            "L": [99.5, 100.5],
            "C": [101.0, 101.5],
            "Vol": [1000, 1200],
            "Symbol": ["ESH26", "ESH26"],
        }
    )


_MAPPING = ColumnMapping(
    timestamp="Time", open="O", high="H", low="L", close="C", volume="Vol", contract_symbol="Symbol"
)


def test_normalizes_to_canonical_columns():
    result = normalize_to_canonical_schema(_raw_vendor_df(), _MAPPING, source_tz="America/New_York")
    assert list(result.columns) == list(CANONICAL_COLUMNS)


def test_normalizes_naive_local_timestamps_to_utc():
    result = normalize_to_canonical_schema(_raw_vendor_df(), _MAPPING, source_tz="America/New_York")
    assert result["timestamp"].iloc[0] == pd.Timestamp("2026-01-15 14:30:00", tz="UTC")


def test_preserves_row_values():
    result = normalize_to_canonical_schema(_raw_vendor_df(), _MAPPING, source_tz="America/New_York")
    assert result["open"].iloc[1] == 101.0
    assert result["contract_symbol"].iloc[0] == "ESH26"
    assert result["volume"].iloc[1] == 1200.0


def test_missing_mapped_column_raises():
    bad_mapping = ColumnMapping(
        timestamp="Time", open="O", high="H", low="L", close="C",
        volume="DoesNotExist", contract_symbol="Symbol",
    )
    with pytest.raises(ValueError):
        normalize_to_canonical_schema(_raw_vendor_df(), bad_mapping, source_tz="America/New_York")


def test_naive_timestamp_without_source_tz_raises():
    with pytest.raises(ValueError):
        normalize_to_canonical_schema(_raw_vendor_df(), _MAPPING)
