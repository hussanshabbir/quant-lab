"""Phase 48: apply the volume-crossover roll logic to real per-contract data.

roll.py's volume_crossover_roll_date was previously only exercised against
synthetic fixtures (see that module's docstring: "NOT YET VALIDATED against
real ES volume data"). This is that validation pass.

Daily volume per contract is built from the real 1-minute bars, correctly
attributed to CME trading dates (not raw UTC calendar dates), with the
Phase 47 known-bad bars (docs/known_gaps.md Gap 3) filtered out first --
several of those bars are exactly the kind of multi-million-contract
phantom volume spike that would otherwise wreck a volume-crossover
comparison.
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
from src.calendar.roll import volume_crossover_roll_date  # noqa: E402
from src.calendar.timestamps import NoTradingDayFoundError, trading_date_for_timestamp  # noqa: E402
from src.ingest.detect_bad_bars import filter_known_bad_bars, load_known_bad_bars  # noqa: E402

DATA_DIR = Path("data/raw/es_futures/ohlcv_1m")
MANIFEST_PATH = Path("data/raw/es_futures/ohlcv_1m_manifest.json")
OUT_PATH = Path("data/raw/es_futures/roll_dates.json")


def daily_volume(symbol: str, calendar: CMEEquityCalendar, known_bad: pd.DataFrame) -> pd.Series:
    df = pd.read_parquet(DATA_DIR / f"{symbol}.parquet").sort_index()
    ts_index = df.index if df.index.tz else df.index.tz_localize("UTC")
    df = df.set_index(ts_index)
    df = filter_known_bad_bars(df, symbol, known_bad)

    trading_dates = {}
    for ts in df.index:
        try:
            trading_dates[ts] = trading_date_for_timestamp(ts, calendar)
        except NoTradingDayFoundError:
            trading_dates[ts] = None
    df["trading_date"] = df.index.map(trading_dates)
    df = df[df["trading_date"].notna()]
    return df.groupby("trading_date")["volume"].sum()


def main() -> int:
    manifest = json.load(open(MANIFEST_PATH))
    symbols_ok = {m["symbol"] for m in manifest["contracts"] if m["status"] == "ok"}

    calendar = CMEEquityCalendar()
    calendar.warm_cache(dt.date(2010, 6, 1), dt.date(2026, 8, 20))
    known_bad = load_known_bad_bars()

    contracts = quarterly_contracts(2010, 2026, calendar)
    contracts = [c for c in contracts if c.symbol in symbols_ok]
    contracts.sort(key=lambda c: c.last_trade_date)

    print(f"Computing daily volume series for {len(contracts)} contracts...")
    vol_by_symbol: dict[str, pd.Series] = {}
    for c in contracts:
        vol_by_symbol[c.symbol] = daily_volume(c.symbol, calendar, known_bad)
        print(f"  {c.symbol}: {len(vol_by_symbol[c.symbol])} trading days")

    results = []
    for front, nxt in zip(contracts, contracts[1:]):
        decision = volume_crossover_roll_date(
            vol_by_symbol[front.symbol], vol_by_symbol[nxt.symbol], confirm_days=1
        )
        days_before_expiry = (front.last_trade_date - decision.roll_date).days if decision else None
        results.append({
            "front": front.symbol,
            "next": nxt.symbol,
            "front_last_trade_date": front.last_trade_date.isoformat(),
            "roll_date": decision.roll_date.isoformat() if decision else None,
            "days_before_front_expiry": days_before_expiry,
            "reason": decision.reason if decision else "no crossover found",
        })
        rd = decision.roll_date if decision else "NONE"
        print(f"{front.symbol} -> {nxt.symbol}: roll_date={rd} "
              f"({days_before_expiry if days_before_expiry is not None else '?'} days before "
              f"{front.symbol} expiry {front.last_trade_date})")

    with open(OUT_PATH, "w") as f:
        json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "transitions": results}, f, indent=2)
    print(f"\nWritten to {OUT_PATH}")

    none_count = sum(1 for r in results if r["roll_date"] is None)
    print(f"\n{len(results)} transitions computed, {none_count} with no crossover found")
    valid_days = [r["days_before_front_expiry"] for r in results if r["days_before_front_expiry"] is not None]
    if valid_days:
        s = pd.Series(valid_days)
        print(f"days_before_front_expiry: min={s.min()} max={s.max()} mean={s.mean():.1f} median={s.median()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
