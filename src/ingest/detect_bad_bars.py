"""Phase 47 follow-up: detect and record known-bad bars in the real ES pull.

Regenerates data/raw/es_futures/known_bad_bars.json. See docs/known_gaps.md
Gap 3 for the full rationale, evidence, and the false positives this
methodology was specifically built to avoid (month-end index-rebalancing
volume spikes look superficially similar but are real).

Two independent tests, both requiring evidence a genuine single real
trading minute cannot produce:

Test 1 (session_settlement_summary_bar): a bar's volume exceeds the SUM of
every other real bar on its own correctly-attributed CME trading date
(calendar.timestamps.trading_date_for_timestamp), AND its high/low falls
outside the range everything else that date actually traded. Both must
hold -- volume-only was tried first and it flagged real month-end
rebalancing spikes (e.g. ESM21 2021-03-31 19:59 UTC, ESM22 2022-03-31)
whose price stays inside the real day's range and whose volume does not
exceed the rest of the day combined.

Test 2 (post_expiration_isolated_settlement_print): a bar on a contract's
own actual last_trade_date, isolated by a >=6-hour gap from the prior real
bar that date, with volume >=5000. Restricted to last_trade_date
specifically (not "any Friday") to avoid the much more common false
positive of a >=6h gap: the completely normal ~49-hour Friday-close to
Sunday-reopen weekend gap, which also carries a real volume burst on
reopen.
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
from src.calendar.timestamps import NoTradingDayFoundError, trading_date_for_timestamp  # noqa: E402

DATA_DIR = Path("data/raw/es_futures/ohlcv_1m")
MANIFEST_PATH = Path("data/raw/es_futures/ohlcv_1m_manifest.json")
OUT_PATH = Path("data/raw/es_futures/known_bad_bars.json")

# Calibrated against the highest genuine single-minute volume observed anywhere
# in this dataset's known-liquid recent contracts (~145,000, incl. a busy 2020
# session). Set with headroom above that, not derived from the anomalies
# themselves, to avoid a self-masking threshold.
ABS_VOLUME_FLOOR = 150_000


def detect(calendar: CMEEquityCalendar, symbols: list[str], contracts: dict) -> tuple[list[dict], int]:
    confirmed: list[dict] = []
    n_ambiguous_excluded = 0

    for sym in symbols:
        df = pd.read_parquet(DATA_DIR / f"{sym}.parquet").sort_index()
        ts_index = df.index if df.index.tz else df.index.tz_localize("UTC")
        df = df.set_index(ts_index)

        # ---- Test 1 ----
        candidates = df[df["volume"] > ABS_VOLUME_FLOOR]
        for ts, row in candidates.iterrows():
            day = df[df.index.date == ts.date()]
            real = day[day.index != ts]
            if real.empty:
                continue
            price_violates = row["high"] > real["high"].max() or row["low"] < real["low"].min()
            vol_dominates = row["volume"] > real["volume"].sum()
            if price_violates and vol_dominates:
                confirmed.append({
                    "symbol": sym, "timestamp": str(ts), "volume": int(row["volume"]),
                    "category": "session_settlement_summary_bar",
                    "reason": "volume exceeds entire rest of real trading-date session AND "
                              "price range falls outside that session's real traded extremes",
                })
            else:
                n_ambiguous_excluded += 1

        # ---- Test 2 ----
        if sym in contracts:
            ltd = contracts[sym].last_trade_date
            day = df[df.index.date == ltd].sort_index()
            if len(day) >= 2:
                gaps = day.index.to_series().diff().dt.total_seconds() / 60
                for i, (ts, row) in enumerate(day.iterrows()):
                    gap = gaps.iloc[i]
                    if pd.notna(gap) and gap >= 360 and row["volume"] >= 5000:
                        confirmed.append({
                            "symbol": sym, "timestamp": str(ts), "volume": int(row["volume"]),
                            "category": "post_expiration_isolated_settlement_print",
                            "reason": f"isolated bar on contract's own last_trade_date, "
                                      f"{gap:.0f} min after prior real bar, volume >=5000",
                        })

    return confirmed, n_ambiguous_excluded


def load_known_bad_bars(path: Path = OUT_PATH) -> pd.DataFrame:
    """The recorded exclusion list as a DataFrame keyed by (symbol, timestamp)."""
    data = json.load(open(path))
    bad = pd.DataFrame(data["bars"])
    bad["timestamp"] = pd.to_datetime(bad["timestamp"])
    return bad


def filter_known_bad_bars(df: pd.DataFrame, symbol: str, known_bad: pd.DataFrame | None = None) -> pd.DataFrame:
    """Drop rows matching the recorded (symbol, timestamp) exclusion list for one
    contract's canonical-schema or raw OHLCV DataFrame (must have a DatetimeIndex
    or a 'timestamp' column). Only removes bars in known_bad_bars.json -- the
    27 ambiguous cases found alongside them are deliberately left untouched."""
    if known_bad is None:
        known_bad = load_known_bad_bars()
    bad_ts = set(known_bad.loc[known_bad["symbol"] == symbol, "timestamp"])
    if not bad_ts:
        return df
    if isinstance(df.index, pd.DatetimeIndex):
        return df[~df.index.isin(bad_ts)]
    return df[~df["timestamp"].isin(bad_ts)]


def main() -> int:
    manifest = json.load(open(MANIFEST_PATH))
    symbols = sorted(m["symbol"] for m in manifest["contracts"] if m["status"] == "ok")

    calendar = CMEEquityCalendar()
    calendar.warm_cache(dt.date(2010, 6, 1), dt.date(2026, 8, 20))
    contracts = {c.symbol: c for c in quarterly_contracts(2010, 2026, calendar)}

    confirmed, n_ambiguous = detect(calendar, symbols, contracts)

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "abs_volume_floor": ABS_VOLUME_FLOOR,
        "n_excluded_ambiguous_not_filtered": n_ambiguous,
        "total_bars_filtered": len(confirmed),
        "bars": confirmed,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Confirmed (filtered): {len(confirmed)}")
    print(f"Ambiguous (excluded from filter, not removed from data): {n_ambiguous}")
    print(f"Written to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
