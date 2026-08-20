"""Phase 66-70: trading simulation, cost model, and fill model for the
surviving strong-group hypotheses (H003, H004, H011, H012 -- the break
events; H001/H002/H009/H010 are the touch versions of the same setups,
see rationale below). DISCOVERY + VALIDATION data only. LOCKED TEST is
never imported or referenced by this module.

PHASE 66 -- RULE DEFINITION (pre-specified, not fit to results)
-----------------------------------------------------------------
Only the BREAK hypotheses are simulated directly. Touch and break are
almost the same population here (H001 touch=77.7% vs H003 break=76.2%;
H002 touch=70.4% vs H004 break=67.8% on the full discovery set) -- the gap
is the near-nonexistent case of a bar's high landing exactly on the prior
level without exceeding it. Break gives an exact, unambiguous entry price
and timestamp (break_high_time/break_low_time); touch alone does not.
Treat H001~H003 and H002~H004 as the same tradeable setup.

There is no strong ex-ante reason to prefer fading a break (mean
reversion) over trading with it (momentum) -- Phase 54/64 only established
that breaks happen more often than a matched random baseline, not which
direction subsequently wins. Rather than pick one after looking at
results, BOTH directions are tested, crossed with two pre-declared
risk/reward multiples (1:1 and 2:1), for a small fixed 2x2 grid per
hypothesis. All 4 cells are reported for all 4 hypotheses -- 16 backtests,
none discarded.

Mechanical rule, identical across all cells except direction/R-multiple:
  - Stop distance = the PRIOR session's own range (prior_high - prior_low)
    -- already fully realized/known at trade time, not fit to any outcome.
  - Target = stop_distance * R_multiple (1x or 2x), in the trade's
    direction.
  - Holding period: exit at the CURRENT session's close if neither stop
    nor target is hit first (time-based exit, session-bounded).
  - MOMENTUM: enter in the direction of the break (long on a high break,
    short on a low break), at the break bar itself (stop-order convention
    -- the order triggers the instant price crosses the level).
  - FADE: enter against the break (short on a high break, long on a low
    break), at the NEXT bar's open after the break bar (the earliest a
    real-time trader could act on a *completed* break bar).

PHASE 67 -- COST MODEL (assumptions stated explicitly)
-----------------------------------------------------------------
  - ES tick size: 0.25 points = $12.50/tick (multiplier $50/point).
  - Commission + exchange/NFA fees: $4.50 round-turn per contract
    (stated assumption -- a moderate, not aggressive, retail/prop
    estimate; CME ES exchange+NFA fees alone run close to $2/side).
  - Slippage: 1 tick per side (entry AND exit), i.e. 2 ticks = $25.00
    round-turn -- applied uniformly to every fill, not just stops, per
    the conservative fill-model philosophy below.
  - Total explicit cost per round-turn trade: $29.50/contract.

PHASE 68 -- FILL MODEL (conservative, bar-level, stated as approximation)
-----------------------------------------------------------------
  - Every fill (entry, stop, or target) gets 1 tick of ADVERSE slippage
    applied against the trader, uniformly -- this is deliberately
    conservative rather than assuming a clean limit fill on profitable
    exits.
  - If a single 1-minute bar's range touches BOTH the stop and the target
    (possible since we only have bar-level OHLC, not tick/quote data),
    the STOP is assumed to have been hit first -- the conservative
    assumption, not the favorable one.
  - This is bar-level, not tick-level: a bar's high/low touching a price
    does not prove a real order would have been filled there with real
    depth and queue position. Treat every number below as an
    approximation directionally biased conservative, not a certified
    fill guarantee.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.research.data_split import VALIDATION_END  # noqa: E402  -- boundary only, no locked_test import

LABELS_PATH = Path("data/raw/es_futures/session_labels.parquet")
GEOMETRY_PATH = Path("data/raw/es_futures/session_geometry.parquet")
BARS_PATH = Path("data/raw/es_futures/continuous_front_month.parquet")
OUT_PATH = Path("data/raw/es_futures/phase66_70_trading_sim_results.json")

TICK_SIZE = 0.25
TICK_VALUE = 12.50
MULTIPLIER = 50.0
COMMISSION_FEES_ROUND_TURN = 4.50
SLIPPAGE_TICKS_PER_SIDE = 1

HYPS = [
    ("H003", "europe_vs_asia", "europe", "high"),
    ("H004", "europe_vs_asia", "europe", "low"),
    ("H011", "ny_vs_europe", "new_york", "high"),
    ("H012", "ny_vs_europe", "new_york", "low"),
]
R_MULTIPLES = [1.0, 2.0]
DIRECTIONS = ["momentum", "fade"]


def simulate_trade(session_bars: np.ndarray, entry_idx: int, entry_price: float,
                    is_long: bool, stop_price: float, target_price: float) -> tuple[float, str]:
    """session_bars: array of (high, low, close) for the current session's
    bars from entry_idx onward (inclusive). Returns (exit_price_raw, reason)."""
    for i in range(entry_idx, len(session_bars)):
        high, low, close = session_bars[i]
        if is_long:
            hit_stop = low <= stop_price
            hit_target = high >= target_price
        else:
            hit_stop = high >= stop_price
            hit_target = low <= target_price

        if hit_stop and hit_target:
            return stop_price, "stop_and_target_same_bar_assume_stop"
        if hit_stop:
            return stop_price, "stop"
        if hit_target:
            return target_price, "target"

    # Neither hit: exit at the last available bar's close (session close)
    return session_bars[-1][2], "session_close"


def apply_slippage(price: float, is_long: bool, entering: bool) -> float:
    """1 tick adverse slippage. Entering long / exiting short = pay up.
    Entering short / exiting long = sell down."""
    adverse_up = (is_long and entering) or (not is_long and not entering)
    return price + TICK_SIZE if adverse_up else price - TICK_SIZE


def run_variant(hyp_id: str, comparison: str, session_name: str, level: str,
                 direction: str, r_multiple: float, labels: pd.DataFrame,
                 geo_open: pd.Series, geo_close: pd.Series, bars_by_date: dict) -> dict:
    break_col = f"broke_{level}"
    break_time_col = f"break_{level}_time"
    sub = labels[(labels["comparison"] == comparison) & (labels[break_col])].copy()

    is_momentum = direction == "momentum"
    is_long = (level == "high") if is_momentum else (level == "low")

    trades = []
    for _, row in sub.iterrows():
        trading_date = row["trading_date"]
        prior_high, prior_low = row["prior_high"], row["prior_low"]
        stop_distance = prior_high - prior_low
        if stop_distance <= 0:
            continue

        session_close_ts = geo_close.get((trading_date, session_name))
        break_time = row[break_time_col]
        day_bars = bars_by_date.get(trading_date)
        if day_bars is None:
            continue
        window = day_bars[(day_bars.index >= break_time) & (day_bars.index < session_close_ts)]
        if window.empty:
            continue
        arr = window[["high", "low", "close"]].to_numpy()

        if is_momentum:
            raw_entry = prior_high if level == "high" else prior_low
            entry_idx = 0
        else:
            if len(window) < 2:
                continue
            raw_entry = window["open"].iloc[1]
            entry_idx = 1
        if entry_idx >= len(arr):
            continue

        entry_price = apply_slippage(raw_entry, is_long, entering=True)
        if is_long:
            stop_price = entry_price - stop_distance
            target_price = entry_price + stop_distance * r_multiple
        else:
            stop_price = entry_price + stop_distance
            target_price = entry_price - stop_distance * r_multiple

        raw_exit, reason = simulate_trade(arr, entry_idx, entry_price, is_long, stop_price, target_price)
        exit_price = apply_slippage(raw_exit, is_long, entering=False)

        points = (exit_price - entry_price) if is_long else (entry_price - exit_price)
        gross_pnl = points * MULTIPLIER  # slippage already embedded in entry_price/exit_price above
        net_pnl = gross_pnl - COMMISSION_FEES_ROUND_TURN  # commission+fees on top of slippage

        trades.append({
            "trading_date": str(trading_date), "reason": reason,
            "gross_pnl": gross_pnl, "net_pnl": net_pnl,
        })

    if not trades:
        return {"n_trades": 0}

    tdf = pd.DataFrame(trades)
    equity = tdf["net_pnl"].cumsum()
    running_max = equity.cummax()
    drawdown = equity - running_max
    max_dd = float(drawdown.min())

    wins = tdf[tdf["net_pnl"] > 0]
    losses = tdf[tdf["net_pnl"] <= 0]

    from scipy.stats import ttest_1samp
    t_result = ttest_1samp(tdf["net_pnl"], 0.0)
    rng = np.random.default_rng(123)
    boot_means = np.array([tdf["net_pnl"].sample(len(tdf), replace=True, random_state=int(rng.integers(1e9))).mean()
                            for _ in range(2000)])
    boot_ci = (float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5)))

    return {
        "n_trades": len(tdf),
        "win_rate": float((tdf["net_pnl"] > 0).mean()),
        "total_net_pnl": float(tdf["net_pnl"].sum()),
        "total_gross_pnl": float(tdf["gross_pnl"].sum()),
        "avg_net_pnl_per_trade": float(tdf["net_pnl"].mean()),
        "avg_win": float(wins["net_pnl"].mean()) if len(wins) else None,
        "avg_loss": float(losses["net_pnl"].mean()) if len(losses) else None,
        "max_drawdown": max_dd,
        "exit_reason_counts": tdf["reason"].value_counts().to_dict(),
        "t_stat_vs_zero": float(t_result.statistic),
        "p_value_vs_zero": float(t_result.pvalue),
        "bootstrap_ci_95_mean_pnl": list(boot_ci),
    }


def main() -> int:
    labels = pd.read_parquet(LABELS_PATH)
    labels = labels[labels["trading_date"] <= VALIDATION_END]  # DISCOVERY + VALIDATION only
    print(f"Discovery+Validation labeled rows: {len(labels)} (locked test excluded, cutoff {VALIDATION_END})")

    geo = pd.read_parquet(GEOMETRY_PATH)
    geo["trading_date"] = pd.to_datetime(geo["trading_date"]).dt.date
    geo_open = geo.set_index(["trading_date", "session"])["utc_open"]
    geo_close = geo.set_index(["trading_date", "session"])["utc_close"]

    bars = pd.read_parquet(BARS_PATH)
    ts_index = bars.index if bars.index.tz else bars.index.tz_localize("UTC")
    bars = bars.set_index(ts_index).sort_index()
    bars = bars[bars["trading_date"] <= VALIDATION_END]

    print("Pre-grouping bars by trading_date for fast per-trade lookup...")
    bars_by_date = {d: g[["open", "high", "low", "close"]] for d, g in bars.groupby("trading_date")}
    print(f"  {len(bars_by_date)} trading dates grouped")

    results = {}
    for hyp_id, comparison, session_name, level in HYPS:
        results[hyp_id] = {}
        for direction in DIRECTIONS:
            for r in R_MULTIPLES:
                key = f"{direction}_R{r:.0f}"
                print(f"Running {hyp_id} {key}...")
                res = run_variant(hyp_id, comparison, session_name, level, direction, r,
                                   labels, geo_open, geo_close, bars_by_date)
                results[hyp_id][key] = res
                if res["n_trades"] > 0:
                    print(f"  n={res['n_trades']}, win_rate={res['win_rate']:.3f}, "
                          f"net_pnl=${res['total_net_pnl']:,.0f}, avg=${res['avg_net_pnl_per_trade']:.2f}, "
                          f"max_dd=${res['max_drawdown']:,.0f}")

    with open(OUT_PATH, "w") as f:
        json.dump({
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "cost_model": {
                "tick_size": TICK_SIZE, "tick_value": TICK_VALUE, "multiplier": MULTIPLIER,
                "commission_fees_round_turn": COMMISSION_FEES_ROUND_TURN,
                "slippage_ticks_per_side": SLIPPAGE_TICKS_PER_SIDE,
            },
            "data_range": f"start -> {VALIDATION_END} (discovery+validation only)",
            "results": results,
        }, f, indent=2, default=str)

    print(f"\nWritten to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
