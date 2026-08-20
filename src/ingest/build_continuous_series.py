"""Phase 48b: splice the real per-contract data into one continuous
front-month series, using Phase 48's empirically-determined roll dates.

Never blindly splices (blueprint Phase 48's own warning): the active
contract for each real trading date comes from `resolve_roll_date`'s
output (docs/known_gaps.md Gap 5), not an assumed days-before-expiry rule.
No price adjustment (back-adjustment/Panama-canal) is applied -- every bar
in the output is exactly the real traded price from its source contract on
that date. This is a deliberate choice: H001-H012 (Phase 51+) compare
sessions WITHIN a single trading day, which by construction uses a single
contract that day, so a roll's price gap never crosses a comparison a
hypothesis actually makes. Introducing a synthetic back-adjusted price
series would mean analyzing non-traded prices for no benefit here.

One transition (ESM26->ESU26) resolves under NEITHER of Phase 48's two
volume-based rules -- not the "interrupted streak" case the majority
fallback was built for, but a genuinely different failure: ESM26's own
real data (per this project's own pull) ends just 4 trading days after
the crossover starts (2026-06-15 -> 06-18), leaving neither rule enough
trailing overlap to confirm on either side. Rather than inventing a third
volume-based tier for one case, this module falls back to the contract's
own documented `last_trade_date` (a real, published CME rule, not a
guess) ONLY for this specific pair, and logs it distinctly in the
manifest so it's auditable, not silently indistinguishable from an
empirically-detected date.
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
from src.calendar.roll import resolve_roll_date  # noqa: E402
from src.calendar.timestamps import NoTradingDayFoundError, trading_date_for_timestamp  # noqa: E402
from src.ingest.detect_bad_bars import filter_known_bad_bars, load_known_bad_bars  # noqa: E402

DATA_DIR = Path("data/raw/es_futures/ohlcv_1m")
MANIFEST_PATH = Path("data/raw/es_futures/ohlcv_1m_manifest.json")
OUT_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")
SEGMENTS_PATH = Path("data/raw/es_futures/continuous_front_month_segments.json")

WINDOW_DAYS = 200
CONFIRM_DAYS = 5
FALLBACK_WINDOW_DAYS = 8


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

    contracts = [c for c in quarterly_contracts(2010, 2026, calendar) if c.symbol in symbols_ok]
    contracts.sort(key=lambda c: c.last_trade_date)

    print(f"Building daily volume series for {len(contracts)} contracts...")
    vol = {c.symbol: daily_volume(c.symbol, calendar, known_bad) for c in contracts}

    # Determine, for each front->next transition, the date the series switches.
    switch_dates: dict[str, dt.date] = {}  # keyed by "front->next"
    fallback_used: dict[str, str] = {}
    for front, nxt in zip(contracts, contracts[1:]):
        window_start = front.last_trade_date - dt.timedelta(days=WINDOW_DAYS)
        fv = vol[front.symbol][vol[front.symbol].index >= window_start]
        nv = vol[nxt.symbol][vol[nxt.symbol].index >= window_start]
        decision = resolve_roll_date(fv, nv, confirm_days=CONFIRM_DAYS, fallback_window_days=FALLBACK_WINDOW_DAYS)
        key = f"{front.symbol}->{nxt.symbol}"
        if decision is not None:
            switch_dates[key] = decision.roll_date
            fallback_used[key] = "fallback" if "majority fallback" in decision.reason else "strict"
        elif front.symbol == "ESM26" and nxt.symbol == "ESU26":
            # Documented one-off: see module docstring. Neither volume rule
            # resolves; fall back to the contract's own published expiration.
            switch_dates[key] = front.last_trade_date
            fallback_used[key] = "last_trade_date_fallback (neither volume rule resolved)"
        else:
            fallback_used[key] = "UNRESOLVED"
        print(f"{key}: switch_date={switch_dates.get(key)} ({fallback_used[key]})")

    # Build the trading_date -> active_symbol map.
    #
    # A contract only gets an active window if we have positive evidence it
    # was ever the front month: either it's the very first contract in the
    # whole sequence (start = dataset start), or the transition INTO it was
    # resolved (strict/fallback/last-trade-date). If the transition into a
    # contract is unresolved (e.g. ESU26->ESZ26 -- it simply hasn't happened
    # yet as of the data's cutoff), that contract is excluded from the
    # continuous series entirely rather than defaulting its start back to
    # the dataset start, which would incorrectly let its own sparse/early
    # trading intermittently overwrite whichever contract is genuinely
    # front month during that period.
    active_symbol_for_date: dict[dt.date, str] = {}
    excluded_unresolved = []
    for i, contract in enumerate(contracts):
        if i == 0:
            start = dt.date(2010, 6, 6)  # dataset start, for the very first contract
        else:
            prev_key = f"{contracts[i-1].symbol}->{contract.symbol}"
            start = switch_dates.get(prev_key)
            if start is None:
                excluded_unresolved.append(contract.symbol)
                continue  # no evidence this contract was ever front month yet

        end = None
        next_key = f"{contract.symbol}->{contracts[i+1].symbol}" if i + 1 < len(contracts) else None
        if next_key is not None:
            end = switch_dates.get(next_key)
        if end is None:
            end = dt.date(2026, 8, 20)  # still the active front month / unresolved future roll

        for d in vol[contract.symbol].index:
            if start <= d < end:
                active_symbol_for_date[d] = contract.symbol

    if excluded_unresolved:
        print(f"Excluded from continuous series (transition into them unresolved): {excluded_unresolved}")

    print(f"\nActive-symbol assignment covers {len(active_symbol_for_date)} trading dates")

    # Assemble the continuous bar series: for each trading date, pull that
    # date's real bars from its assigned active contract.
    frames = []
    segments = []
    current_symbol = None
    segment_start = None
    for d in sorted(active_symbol_for_date):
        sym = active_symbol_for_date[d]
        if sym != current_symbol:
            if current_symbol is not None:
                segments.append({"symbol": current_symbol, "start": str(segment_start), "end": str(prev_d)})
            current_symbol = sym
            segment_start = d
        prev_d = d
    if current_symbol is not None:
        segments.append({"symbol": current_symbol, "start": str(segment_start), "end": str(prev_d)})

    print(f"{len(segments)} contract segments in the continuous series")

    by_symbol_dates: dict[str, set] = {}
    for d, sym in active_symbol_for_date.items():
        by_symbol_dates.setdefault(sym, set()).add(d)

    for sym, dates in by_symbol_dates.items():
        df = pd.read_parquet(DATA_DIR / f"{sym}.parquet").sort_index()
        ts_index = df.index if df.index.tz else df.index.tz_localize("UTC")
        df = df.set_index(ts_index)
        df = filter_known_bad_bars(df, sym, known_bad)
        trading_dates = {}
        for ts in df.index:
            try:
                trading_dates[ts] = trading_date_for_timestamp(ts, calendar)
            except NoTradingDayFoundError:
                trading_dates[ts] = None
        df["trading_date"] = df.index.map(trading_dates)
        df = df[df["trading_date"].isin(dates)]
        df["source_contract"] = sym
        frames.append(df[["open", "high", "low", "close", "volume", "trading_date", "source_contract"]])

    continuous = pd.concat(frames).sort_index()
    dup_count = continuous.index.duplicated().sum()
    if dup_count:
        print(f"WARNING: {dup_count} duplicate timestamps across segments -- investigate before use")

    continuous.to_parquet(OUT_PATH)
    with open(SEGMENTS_PATH, "w") as f:
        json.dump({
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "n_segments": len(segments),
            "switch_dates": {k: str(v) for k, v in switch_dates.items()},
            "fallback_used": fallback_used,
            "segments": segments,
        }, f, indent=2)

    print(f"\nContinuous series: {len(continuous)} bars, {continuous['trading_date'].nunique()} trading dates")

    from collections import Counter
    seg_counts = Counter(s["symbol"] for s in segments)
    split_symbols = {k: v for k, v in seg_counts.items() if v > 1}
    if split_symbols:
        print(f"WARNING: {len(split_symbols)} symbol(s) appear in more than one non-contiguous "
              f"segment -- investigate before trusting this series: {split_symbols}")
    else:
        print(f"Sanity check passed: every contract contributes exactly one contiguous segment "
              f"({len(segments)} segments for {len(by_symbol_dates)} contracts used)")

    print(f"Written to {OUT_PATH}")
    print(f"Segments written to {SEGMENTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
