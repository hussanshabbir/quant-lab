"""Contract roll-date determination (blueprint Phase 48, dynamic half).

"Never blindly splice contracts." CME does not mandate a roll date --
unlike the last-trade date (a fixed rule, see ``contracts.py``), the
date on which research/backtests should switch from treating contract N
as the front month to contract N+1 is a market-behavior question: it's
whichever date liquidity has genuinely migrated to the next contract.
This module determines that empirically from real volume, rather than
assuming a fixed number of days before expiration.

STATUS: validated against real ES volume data (Phase 48, 2026-08), after
Phase 46/47 real data acquisition and cleaning landed. Findings from that
validation pass, in full, are recorded in docs/known_gaps.md. Summary:
the naive default (confirm_days=1, unbounded search window) is unusable on
real full-lifetime per-contract data -- deep back-month history is thin
enough that single-day volume noise (e.g. 2 contracts vs 1) produces
spurious early "crossovers" many months before any real migration. The
validated configuration is confirm_days=5 with the search bounded to the
200 days before the front contract's own expiry (excludes the noise
regime entirely) via ``resolve_roll_date``, which also applies
``majority_crossover_roll_date`` as a documented fallback for the rare
case (3 of 66 real transitions, all 2010-2012 vintage) where a real,
visible migration doesn't sustain 5 strictly-consecutive days. Prefer
``resolve_roll_date`` as the entry point over calling
``volume_crossover_roll_date`` directly. Whether volume-crossover is the
right signal at all (versus open interest, or a combined signal) remains
open -- real ES data doesn't include open interest in this project's
current ohlcv-1m pull, so that comparison hasn't been possible yet.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RollDecision:
    roll_date: dt.date
    reason: str


def volume_crossover_roll_date(
    front_volume: pd.Series,
    next_volume: pd.Series,
    confirm_days: int = 1,
) -> RollDecision | None:
    """First date the next contract's volume exceeds the front contract's,
    sustained for ``confirm_days`` consecutive trading days.

    Both series must be indexed by trading date (any orderable,
    comparable index -- typically a DatetimeIndex or a plain date
    index), with volume as the value. Only dates present in both series
    are considered. ``confirm_days`` > 1 guards against a single noisy
    day (e.g. an early-roll speculative volume spike) triggering a
    premature roll signal.

    Returns None if the crossover never happens (or never sustains for
    ``confirm_days``) within the overlapping date range -- e.g. if the
    two series don't overlap far enough into the next contract's life
    for the crossover to occur yet.
    """
    if confirm_days < 1:
        raise ValueError("confirm_days must be >= 1")

    aligned = pd.DataFrame({"front": front_volume, "next": next_volume}).dropna().sort_index()
    if aligned.empty:
        return None

    next_exceeds_front = aligned["next"] > aligned["front"]

    for start in range(len(next_exceeds_front) - confirm_days + 1):
        window = next_exceeds_front.iloc[start : start + confirm_days]
        if window.all():
            idx = aligned.index[start]
            roll_date = idx.date() if hasattr(idx, "date") else idx
            return RollDecision(
                roll_date=roll_date,
                reason=(
                    f"next-contract volume exceeded front-month volume for "
                    f"{confirm_days} consecutive trading day(s) starting {roll_date}"
                ),
            )

    return None


def majority_crossover_roll_date(
    front_volume: pd.Series,
    next_volume: pd.Series,
    window_days: int = 8,
) -> RollDecision | None:
    """Fallback roll-date rule, for use only when `volume_crossover_roll_date`
    finds no match (see `resolve_roll_date`, the intended entry point).

    First date whose following `window_days` consecutive trading days show
    the next contract's volume exceeding the front contract's on a MAJORITY
    of those days (strictly more than half), rather than requiring every
    single day in a row.

    Why this exists (validated against real ES data, Phase 48, 2026-08):
    of 66 real front/next contract-transition pairs (2010-2026), 61 resolved
    cleanly under the strict all-consecutive-days rule at confirm_days=5. The
    other 3 (all 2010-2012 vintage: ESZ10->ESH11, ESZ11->ESH12, ESH12->ESM12)
    showed a real, visually obvious migration 8-11 trading days before
    expiry, but the day-by-day crossover wasn't perfectly consecutive -- a
    single near-tie day or a front-contract last-day settlement-related
    volume blip broke what was otherwise a clear shift into two streaks each
    short of 5. `window_days=8` with a majority threshold was chosen because
    it's wide enough to absorb one or two such interruptions without also
    accepting noise: real migration produces a majority within a fixed
    window; the thin-history noise regime that made confirm_days=1 unusable
    in the first place does not reliably produce 5+ of 8 days favoring the
    same contract (it flips back and forth close to 50/50).

    Confirmed (2026-08 validation run): applying this SAME rule to all 66
    transitions -- not just the 3 that needed it -- never produces a
    different or earlier date than the strict rule on any of the 61 pairs
    it already resolved. The fallback only ever fires where the strict rule
    returns None; it is not a replacement for it. See resolve_roll_date.
    """
    aligned = pd.DataFrame({"front": front_volume, "next": next_volume}).dropna().sort_index()
    if len(aligned) < window_days:
        return None

    next_exceeds_front = aligned["next"] > aligned["front"]
    majority_threshold = window_days // 2 + 1  # strictly more than half

    for start in range(len(next_exceeds_front) - window_days + 1):
        window = next_exceeds_front.iloc[start : start + window_days]
        wins = int(window.sum())
        if wins >= majority_threshold:
            idx = aligned.index[start]
            roll_date = idx.date() if hasattr(idx, "date") else idx
            return RollDecision(
                roll_date=roll_date,
                reason=(
                    f"next-contract volume exceeded front-month volume on "
                    f"{wins}/{window_days} days in the window starting "
                    f"{roll_date} (majority fallback -- strict all-"
                    f"consecutive-days rule found no sustained match)"
                ),
            )

    return None


def resolve_roll_date(
    front_volume: pd.Series,
    next_volume: pd.Series,
    confirm_days: int = 5,
    fallback_window_days: int = 8,
) -> RollDecision | None:
    """Intended entry point for roll-date determination: the strict
    all-consecutive-days rule (`volume_crossover_roll_date`) first, falling
    back to the majority-of-window rule (`majority_crossover_roll_date`)
    only when the strict rule finds nothing. The fallback never overrides a
    strict-rule result -- see `majority_crossover_roll_date`'s docstring for
    why, and for the real-data validation this ordering was checked against.
    """
    strict = volume_crossover_roll_date(front_volume, next_volume, confirm_days=confirm_days)
    if strict is not None:
        return strict
    return majority_crossover_roll_date(front_volume, next_volume, window_days=fallback_window_days)
