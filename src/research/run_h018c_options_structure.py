"""H018c: monetizing H018b's volatility-persistence signal via a long
SPX straddle. Pre-registered design -- see the chat message accompanying
this script.

  Signal: same as H018b -- ratio(t) = |ES return(t)| / (VIX_close(t-1)/16)
  >= threshold in {1.5, 2.0}, using already-validated discovery-period
  trigger dates.

  Entry: next trading day's OPEN (t+1) -- buy 1 ATM call + 1 ATM put
  (nearest listed strike to prior close), nearest expiration >= 10
  trading days out (covers both horizons with one consistent position).

  Exit / mark: CLOSE of the 5th and 10th trading day after entry
  (H018b's two pre-declared horizons), marking the SAME position at both
  points rather than opening two differently-dated positions.

  Costs: real trade prints (ohlcv-1d open/close) for the underlying P&L,
  with a conservative round-trip cost haircut per leg grounded in real
  SPX quotes measured just before this run (call spread 0.46% median,
  put spread 2.8% on an admittedly not-quite-ATM strike) -- applying
  4% round-trip cost PER LEG (8% total across both legs) as the stated,
  conservative assumption, consistent with how ES's cost model was a
  stated verified assumption rather than a per-trade quote-cross.

  Baseline: identical mechanic on a matched-count RANDOM sample of
  non-trigger discovery-period dates, to isolate whether the SIGNAL adds
  value beyond generically owning a straddle.

  4 variants (2 thresholds -- inherited from which trigger set the entry
  dates come from -- x 2 horizons), Bonferroni + BH.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.research.data_split import DISCOVERY_END, DISCOVERY_START  # noqa: E402

OUT_DIR = Path("data/raw/vix")
ROUND_TRIP_COST_PER_LEG = 0.04  # 4% of premium, stated conservative assumption
HORIZONS = [5, 10]
# OPRA.PILLAR's real data coverage starts 2013-04-01 -- confirmed via a live
# API error, not assumed. H018b's signal was validated on the full 2010-2021
# discovery window; this options-monetization test can only run on the
# 2013-2021 subset. Documented explicitly, not silently dropped.
OPRA_COVERAGE_START = dt.date(2013, 4, 1)


def get_client():
    import os
    import databento as db
    return db.Historical(os.environ["DATABENTO_API_KEY"])


def trading_days_after(all_dates: list, ref_date: dt.date, n: int) -> dt.date | None:
    idx = np.searchsorted(all_dates, ref_date)
    target_idx = idx + n
    if target_idx >= len(all_dates):
        return None
    return all_dates[target_idx]


def find_straddle_contract(client, entry_date: dt.date, atm_price: float, min_expiry_days_out: dt.date):
    """Pull real definitions as of entry_date, find nearest strike + nearest
    expiration >= min_expiry_days_out. Returns (call_symbol, put_symbol, strike, expiry) or None."""
    import databento as db
    start = entry_date.isoformat()
    end = (entry_date + dt.timedelta(days=1)).isoformat()
    try:
        store = client.timeseries.get_range(
            dataset="OPRA.PILLAR", symbols="SPX.OPT", schema="definition",
            start=start, end=end, stype_in="parent",
        )
    except db.common.error.BentoError as e:
        print(f"    [definitions pull failed for {entry_date}: {e}]")
        return None
    df = store.to_df()
    if df.empty:
        print(f"    [no definitions returned for {entry_date}]")
        return None
    # instrument_class 'C'/'P' here means Call/Put (options convention, distinct
    # from futures' F/S convention seen elsewhere in this project) -- keep only
    # standard single-leg options, not multi-leg combos, to avoid duplicate/odd
    # strike listings from spread definitions.
    df = df[df["instrument_class"].isin(["C", "P"])].reset_index(drop=True)
    df["expiration_date"] = df["expiration"].dt.date
    candidates = df[df["expiration_date"] >= min_expiry_days_out]
    if candidates.empty:
        print(f"    [no expirations >= {min_expiry_days_out} found for {entry_date}]")
        return None
    target_expiry = candidates["expiration_date"].min()
    same_exp = df[df["expiration_date"] == target_expiry].drop_duplicates(subset=["strike_price"]).reset_index(drop=True)
    if same_exp.empty:
        return None
    strike_diff = (same_exp["strike_price"] - atm_price).abs()
    best_strike = float(same_exp.loc[strike_diff.idxmin(), "strike_price"])
    strike_int = int(round(best_strike * 1000))
    strike_str = f"{strike_int:08d}"
    call_sym = f"SPX   {target_expiry.strftime('%y%m%d')}C{strike_str}"
    put_sym = f"SPX   {target_expiry.strftime('%y%m%d')}P{strike_str}"
    return call_sym, put_sym, best_strike, target_expiry


def pull_daily_bars(client, symbols: list, start: dt.date, end: dt.date, max_attempts=3):
    import databento as db
    for attempt in range(max_attempts):
        try:
            store = client.timeseries.get_range(
                dataset="OPRA.PILLAR", symbols=symbols, schema="ohlcv-1d",
                start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat(), stype_in="raw_symbol",
            )
            return store.to_df()
        except db.common.error.BentoError:
            time.sleep(2)
    return pd.DataFrame()


def main() -> int:
    client = get_client()

    trig15_all = [dt.date.fromisoformat(d) for d in json.load(open(OUT_DIR / "h018c_trigger_dates_15x.json"))]
    trig20 = set(dt.date.fromisoformat(d) for d in json.load(open(OUT_DIR / "h018c_trigger_dates_20x.json")))

    trig15 = [d for d in trig15_all if d >= OPRA_COVERAGE_START]
    n_excluded = len(trig15_all) - len(trig15)
    print(f"OPRA coverage filter: {n_excluded} of {len(trig15_all)} trigger dates excluded "
          f"(before {OPRA_COVERAGE_START}), {len(trig15)} remain")

    bars = pd.read_parquet("data/raw/es_futures/continuous_front_month.parquet")
    daily_close = bars.groupby("trading_date")["close"].last().sort_index()
    all_trading_dates = sorted(daily_close.index)
    disc_dates = [d for d in all_trading_dates if max(DISCOVERY_START, OPRA_COVERAGE_START) <= d <= DISCOVERY_END]

    rng = np.random.default_rng(2026)
    non_trigger_pool = [d for d in disc_dates if d not in set(trig15_all)]
    baseline_dates = list(rng.choice(non_trigger_pool, size=len(trig15), replace=False))

    def build_event(trigger_date: dt.date) -> dict | None:
        entry_date = trading_days_after(all_trading_dates, trigger_date, 1)
        if entry_date is None or entry_date > DISCOVERY_END:
            return None
        exit_10d = trading_days_after(all_trading_dates, entry_date, 10)
        if exit_10d is None:
            return None
        exit_5d = trading_days_after(all_trading_dates, entry_date, 5)
        min_expiry = exit_10d
        atm_price = float(daily_close.loc[entry_date])

        contract = find_straddle_contract(client, entry_date, atm_price, min_expiry)
        if contract is None:
            return None
        call_sym, put_sym, strike, expiry = contract

        bars_df = pull_daily_bars(client, [call_sym, put_sym], entry_date, exit_10d)
        if bars_df.empty:
            print(f"    [no bars for {call_sym}/{put_sym} in {entry_date}..{exit_10d}]")
            return None
        bars_df = bars_df.reset_index()
        bars_df["date"] = pd.to_datetime(bars_df["ts_event"]).dt.date

        def price_at(sym, date, field):
            row = bars_df[(bars_df["symbol"] == sym) & (bars_df["date"] == date)]
            return float(row[field].iloc[0]) if len(row) else None

        call_entry = price_at(call_sym, entry_date, "open")
        put_entry = price_at(put_sym, entry_date, "open")
        call_5d = price_at(call_sym, exit_5d, "close") if exit_5d else None
        put_5d = price_at(put_sym, exit_5d, "close") if exit_5d else None
        call_10d = price_at(call_sym, exit_10d, "close")
        put_10d = price_at(put_sym, exit_10d, "close")

        if None in (call_entry, put_entry, call_10d, put_10d):
            print(f"    [missing entry/exit prints for {call_sym}/{put_sym}: "
                  f"call_entry={call_entry}, put_entry={put_entry}, call_10d={call_10d}, put_10d={put_10d}]")
            return None

        return {
            "trigger_date": str(trigger_date), "entry_date": str(entry_date),
            "exit_5d_date": str(exit_5d) if exit_5d else None, "exit_10d_date": str(exit_10d),
            "call_symbol": call_sym, "put_symbol": put_sym, "strike": strike, "expiry": str(expiry),
            "call_entry": call_entry, "put_entry": put_entry,
            "call_5d": call_5d, "put_5d": put_5d, "call_10d": call_10d, "put_10d": put_10d,
        }

    def pnl(event: dict, horizon: int) -> float | None:
        if horizon == 5:
            call_exit, put_exit = event["call_5d"], event["put_5d"]
        else:
            call_exit, put_exit = event["call_10d"], event["put_10d"]
        if call_exit is None or put_exit is None:
            return None
        entry_cost = event["call_entry"] * (1 + ROUND_TRIP_COST_PER_LEG / 2) + event["put_entry"] * (1 + ROUND_TRIP_COST_PER_LEG / 2)
        exit_proceeds = call_exit * (1 - ROUND_TRIP_COST_PER_LEG / 2) + put_exit * (1 - ROUND_TRIP_COST_PER_LEG / 2)
        return (exit_proceeds - entry_cost) / entry_cost  # % return on the straddle premium

    print(f"Building {len(trig15)} trigger events + {len(baseline_dates)} baseline events...")
    trigger_events = []
    for i, d in enumerate(trig15):
        ev = build_event(d)
        if ev:
            ev["is_2x"] = d in trig20
            trigger_events.append(ev)
        if (i + 1) % 20 == 0:
            print(f"  trigger events: {i+1}/{len(trig15)} processed, {len(trigger_events)} succeeded")

    baseline_events = []
    for i, d in enumerate(baseline_dates):
        ev = build_event(d)
        if ev:
            baseline_events.append(ev)
        if (i + 1) % 20 == 0:
            print(f"  baseline events: {i+1}/{len(baseline_dates)} processed, {len(baseline_events)} succeeded")

    with open(OUT_DIR / "h018c_trigger_events.json", "w") as f:
        json.dump(trigger_events, f, indent=2, default=str)
    with open(OUT_DIR / "h018c_baseline_events.json", "w") as f:
        json.dump(baseline_events, f, indent=2, default=str)

    print(f"\nFinal: {len(trigger_events)} trigger events, {len(baseline_events)} baseline events with complete data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
