"""Phase 49-50: real Asia/Europe/New York session construction + geometry,
run against the Phase 48b continuous front-month series -- the first real
(not synthetic-test) exercise of sessions.py and session_geometry.py.

For each real CME trading date in the continuous series, builds the three
session windows (sessions.py) and computes OHLCV/VWAP/range/high-low-time
geometry for each (session_geometry.py). Sessions with zero real bars
(EmptySessionError) are recorded as missing, not fabricated -- this
happens legitimately in the earliest, thinnest years of the dataset,
particularly the Asia window.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.calendar.exchange import CMEEquityCalendar  # noqa: E402
from src.calendar.session_geometry import (  # noqa: E402
    DuplicateBarsError,
    EmptySessionError,
    compute_session_geometry,
)
from src.calendar.sessions import build_day_sessions  # noqa: E402

DATA_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")
OUT_PATH = Path("data/raw/es_futures/session_geometry.parquet")
MISSING_LOG_PATH = Path("data/raw/es_futures/session_geometry_missing.json")


def main() -> int:
    df = pd.read_parquet(DATA_PATH)
    ts_index = df.index if df.index.tz else df.index.tz_localize("UTC")
    df = df.set_index(ts_index).sort_index()

    calendar = CMEEquityCalendar()
    trading_dates = sorted(df["trading_date"].unique())
    calendar.warm_cache(trading_dates[0] - dt.timedelta(days=3), trading_dates[-1] + dt.timedelta(days=3))

    print(f"Computing session geometry for {len(trading_dates)} real trading dates...")

    rows = []
    missing = []
    for i, trading_date in enumerate(trading_dates):
        day_bars = df[df["trading_date"] == trading_date]
        day_sessions = build_day_sessions(trading_date, calendar)
        if day_sessions is None:
            missing.append({"trading_date": str(trading_date), "session": "ALL", "reason": "full_holiday"})
            continue

        for name, session in day_sessions.items():
            try:
                geo = compute_session_geometry(day_bars, session)
            except EmptySessionError:
                missing.append({"trading_date": str(trading_date), "session": name, "reason": "empty_session"})
                continue
            except DuplicateBarsError as exc:
                missing.append({"trading_date": str(trading_date), "session": name, "reason": f"duplicate_bars: {exc}"})
                continue

            rows.append({
                "trading_date": trading_date, "session": name,
                "utc_open": geo.utc_open, "utc_close": geo.utc_close,
                "open": geo.open, "high": geo.high, "low": geo.low, "close": geo.close,
                "high_time": geo.high_time, "low_time": geo.low_time,
                "volume": geo.volume, "vwap": geo.vwap, "range": geo.range,
                "bar_count": geo.bar_count, "zero_volume_bar_count": geo.zero_volume_bar_count,
                "was_clipped": session.was_clipped, "clip_reason": session.clip_reason,
            })

        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(trading_dates)} dates processed")

    result = pd.DataFrame(rows)
    result.to_parquet(OUT_PATH)
    with open(MISSING_LOG_PATH, "w") as f:
        json.dump({
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "n_trading_dates": len(trading_dates),
            "n_sessions_expected": len(trading_dates) * 3,
            "n_sessions_computed": len(result),
            "n_missing": len(missing),
            "missing": missing,
        }, f, indent=2, default=str)

    print(f"\nSessions computed: {len(result)} / {len(trading_dates)*3} expected")
    print(f"Missing: {len(missing)}")
    by_session_missing = pd.Series([m["session"] for m in missing]).value_counts()
    print("Missing by session:")
    print(by_session_missing)
    by_reason = pd.Series([m["reason"] for m in missing]).value_counts()
    print("Missing by reason:")
    print(by_reason)
    print(f"\nWritten to {OUT_PATH}")
    print(f"Missing log written to {MISSING_LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
