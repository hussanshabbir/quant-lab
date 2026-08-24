# Hypothesis findings log

Per blueprint Phase 86 (research governance): every experiment gets permanently
recorded, including closed-out hypotheses that never reached a full test --
a feasibility check that kills an idea before spending on it is still a real
result worth keeping on record, not a null event to forget. Distinct from
`docs/known_gaps.md` / `docs/known_gaps_equities.md`, which track data and
methodology defects -- this file tracks hypothesis outcomes.

## H016 -- earnings-driven option momentum (closed 2026-08-22, spread evidence only)

**Status: closed, not pursued further.** Killed on a cost feasibility check
before the full dataset was pulled -- the best-case reading of the evidence
already fails decisively, so spending the remaining budget to confirm a worse
number on less liquid names was not worth it.

### The idea
Buy a near-the-money call on an earnings beat / put on an earnings miss
(surprise >= 5%), at the next trading day's open, sell at midday -- on the
theory that a large, real earnings surprise produces a persistent morning
directional drift large enough to profit from after costs.

### Full pre-registration (kept on record in case this is worth revisiting)
- **Universe (50 tickers)**: top-50 by average daily dollar volume among the
  H015 decisive-venue equity universe, over Q1 2019 -- an objective,
  lookahead-free liquidity proxy computed before seeing any earnings/options
  data. AMZN, AAPL, MSFT, FB, NFLX, TSLA, GOOGL, NVDA, GOOG, INTC, AMD, CSCO,
  AVGO, MU, ADBE, CELG, BKNG, CMCSA, PEP, QCOM, AMGN, PYPL, SBUX, TXN, EA,
  BIIB, AABA, COST, GILD, ATVI, CHTR, LRCX, XLNX, WBA, FISV, FOXA, INTU, ADP,
  ISRG, AMAT, ALGN, EBAY, CSX, CME, KHC, NXPI, WDAY, MDLZ, ADI, WDC.
- **Trigger**: |actual EPS - estimate| / |estimate| >= 5%.
- **Entry/exit**: reaction day R = next trading day if reported after close,
  same day if reported before open. Buy at R's 09:30 ET open; sell at
  12:00:00 ET exactly. Call on beat, put on miss. Strike = nearest listed to
  prior close (no lookahead); expiration = nearest listed on/after R.
- **Baselines** (pre-declared, not yet run): (a) same mechanic on
  non-earnings days for the same stock, to isolate the earnings-specific
  effect from generic option volatility; (b) earnings days with a fixed
  direction regardless of actual surprise sign, to isolate whether the
  beat/miss *direction* calibration adds anything beyond "earnings days are
  volatile."
- **Split**: 2019-2021 discovery, 2022 validation, 2023 locked test.
- **Data sourcing confirmed feasible**: earnings surprise data free via
  Financial Modeling Prep or Alpha Vantage; options data via Databento's
  `OPRA.PILLAR` (the real consolidated options tape, 2013-04-01 onward --
  not a fragmented single-venue feed like the equities problem in H015/Gap
  3). Estimated full-dataset cost at this scope: ~$24.

### Why it was killed: the spread-check evidence
Pulled real consolidated quotes (`cmbp-1`) for near-the-money options on
**AAPL and MSFT specifically** -- the two most liquid single-stock options
in the entire US market, the most favorable case this hypothesis could ever
get:

| Contract | Median spread (% of premium) |
|---|---|
| AAPL call (NTM) | 3.58% |
| AAPL put (NTM) | 3.86% |
| MSFT call (NTM) | 5.39% |
| MSFT put (near-strike, thin) | 17.39% |

Round-trip spread cost of 3.6-5.4% of the option's own premium, even on the
best-liquidity names available, dwarfs anything survived in H001-H015 (which
all involved cost hurdles of a few ticks/bps against the underlying, not
several percent of the entire position value). The other 48 names in the
universe were selected for high liquidity but are still expected to have
wider options markets than AAPL/MSFT, not tighter -- so 3.6-5.4% is a
best-case reading, not a representative one. For this hypothesis to survive,
the earnings-reaction move would need to reliably clear a cost hurdle far
higher than anything found to be real in this project so far.

**Decision: not pulling the full ~$24 dataset.** The best-case number already
fails decisively; a worse, more representative number from the full universe
would not change the conclusion, only confirm it at a cost. Budget preserved.

### Possible future direction (flagged, not being chased now)
The spread cost above is asymmetric -- it's a cost to whoever is *buying*
the option (crossing the spread to enter and exit), and correspondingly
income to whoever is *selling* (writing) it. A structurally different version
of this idea -- selling premium into the earnings reaction rather than buying
it -- flips who collects the spread rather than who pays it, which could
plausibly change the economics enough to be worth a fresh feasibility check
on its own terms. Not pursued as part of H016; would need its own
pre-registration (a written-option strategy has a fundamentally different
risk profile -- defined income, undefined/large loss tail -- and shouldn't
be treated as "H016 but flipped" without thinking through that separately).
This is a note for a future session, not a next step in this one.

## H017 -- COT Leveraged Funds crowding -> ES forward return (closed 2026-08-22)

**Status: closed, dead on arrival.** No trading-sim/cost step needed --
this failed the raw statistical test, not the cost test.

### Design (pre-registered before running)
Free data: CFTC Traders in Financial Futures report, `E-MINI S&P 500`
contract, `lev_money_positions_long/short` (the actual CFTC category name
for hedge funds/CTAs -- the closest public proxy to "speculative
crowding"). Pulled via `publicreporting.cftc.gov`'s Socrata API (dataset
`gpe5-46if`), 1,054 weekly observations, 2006-06-13 to 2026-08-18 --
covers the full ES discovery window with room to spare.

Signal: net Leveraged Funds position as % of open interest, ranked
against its own trailing 104-week (2-year) history (self-calibrating, not
a fixed cutoff). Tested at 2 pre-declared percentile thresholds (10%,
20%) x 2 pre-declared forward horizons (1 week, 4 weeks) = 4 variants,
Bonferroni+BH across all 4. Hypothesis: extreme long positioning (crowded
trade) predicts lower forward returns than extreme short positioning
(mean reversion / "who's left to buy").

### Result
| Threshold | Horizon | Diff (long extreme - short extreme) | Right direction? | p-value |
|---|---|---|---|---|
| 10% | 1wk | +15.3 bps | No | 0.63 |
| 10% | 4wk | +29.8 bps | No | 0.66 |
| 20% | 1wk | -10.1 bps | Yes | 0.69 |
| 20% | 4wk | +17.7 bps | No | 0.75 |

3 of 4 variants point the *wrong* direction (crowded longs followed by
*higher* returns, not lower). None significant, none survive correction,
none close to either bar. This is a clean null, not a "real but too
small" result -- no detectable relationship in this formulation.

### Not chased, logged for later if ever revisited
Untested alternative cuts, explicitly not pursued now to avoid
after-the-fact variant hunting: Asset Manager positioning instead of
Leveraged Funds; week-over-week *change* in positioning rather than
level; other instruments (currencies, rates) where COT-based crowding
signals are also commonly discussed in practitioner literature.

## H018 -- VIX/16 realized-vs-implied divergence (closed/split 2026-08-22)

**Status: the directional reading is dead; the volatility-persistence
reading survived everything thrown at it -- the strongest, most robust
result in this project to date.** Not yet a P&L-quotable strategy; is
already a validated risk-sizing input.

### Design (pre-registered before running, free data throughout)
`implied_move(t) = VIX_close(t-1) / 16` (yesterday's close, matching the
"before market opens" framing exactly, no lookahead). `ratio(t) =
realized_move(t) / implied_move(t)`. VIX data: official CBOE historical
CSV, free, 1990-2026. ES data: existing validated continuous front-month
series. Zero new spend.

### H018 (directional continuation) -- dead
Tested: does `sign(return(t+H)) == sign(return(t))` for H in {1, 5} days,
at ratio thresholds {1.5, 2.0}, vs. permutation baseline. All 4 variants:
lift within +/-6bps of zero, p in [0.41, 1.00]. Not close, no correction
needed to reject.

### H018b (volatility persistence) -- survived, real
Tested: forward average |daily return| over the next H in {5, 10} days
after a trigger, vs. permutation baseline. **All 4 variants hit the
permutation floor (p=0.0005) and survive both Bonferroni and BH:**

| Threshold | Horizon | Lift vs. baseline |
|---|---|---|
| 1.5x | 5d | +48.4 bps/day (baseline 67.3) |
| 1.5x | 10d | +42.7 bps/day (baseline 67.4) |
| 2.0x | 5d | +74.0 bps/day (baseline 67.6) |
| 2.0x | 10d | +63.0 bps/day (baseline 67.2) |

Year-by-year stability (2010-2021, the full check): trigger days present
in **12 of 12 years** (never zero), positive lift in **11 of 12** (2012
the lone exception, -3.3bps, noise-level). 2020 (COVID) shows the largest
lift (+175bps) but the effect holds in completely ordinary years too
(2013: +6.0, 2014: +17.6, 2016: +18.7, 2017: +6.7, 2019: +30.6) --
not a crisis-year artifact.

### What this is and isn't
Real: a realized-vs-implied divergence of ~1.5-2x reliably precedes 1-2
weeks of meaningfully elevated volatility (60-110% above the year's own
typical level). Not directional -- H018 ruled that out specifically.
**Already actionable as-is for risk management** (position sizing, stop
width) without further work. **Not yet validated as a P&L strategy** --
monetizing it (e.g. a long-vol options structure ahead of the expected
pickup) is untested and would need its own cost verification given H016
already showed options spread costs (3.6-19% round-trip even on the most
liquid names) can dominate a plausible edge. Not assuming it survives
that step just because the underlying signal is real.

## H018c -- monetizing H018b via a long SPX straddle (closed 2026-08-22)

**Status: closed. Signal (H018b) stands; this specific monetization does
not.** First real result in this project built on top of an already-
validated finding rather than starting fresh -- worth recording precisely
because the underlying signal being real did NOT save the trade.

### Design (pre-registered before pulling anything)
Entry: next trading day's open after a trigger (ratio >= 1.5 or 2.0, same
as H018b). Long 1 ATM call + 1 ATM put (straddle), nearest strike to
prior close, nearest expiration >= 10 trading days out. Mark-to-market
at the close of the 5th and 10th trading day after entry (both horizons
priced off the SAME position, not two separately-opened trades). Costs:
4% round-trip per leg (8% total), a stated conservative assumption
grounded in real SPX quotes measured the same session (median call
spread 0.46%, put spread 2.8% on an admittedly not-quite-ATM strike --
4%/leg deliberately pads well above both). Baseline: identical mechanic
on a matched-count random sample of non-trigger discovery-period dates.
Instrument: SPX via OPRA (not GLBX.MDP3, which was still unresolved at
the time).

### Real, important data-coverage finding
**OPRA.PILLAR's actual data start is 2013-04-01** (confirmed via a live
422 error, not assumed) -- well after H018b's full 2010-2021 discovery
window. 46 of 166 1.5x trigger dates were excluded for predating this;
120 remained, of which 99 (82.5%) had complete real historical option
data (strike/expiration resolved + all entry/exit prints present). The
underlying H018b signal is still validated on the full 2010-2021 window;
only this specific options-monetization test is restricted to 2013-2021.

### Result -- none of 4 pre-registered variants survive correction
| Threshold | Horizon | Trigger mean | Baseline mean | Diff | p (t-test) | Survives correction |
|---|---|---|---|---|---|---|
| 1.5x | 5d | -8.51% | -10.65% | +2.14% | 0.49 | No |
| 1.5x | 10d | -0.30% | -15.50% | +15.20% | 0.021 (raw) | **No** |
| 2.0x | 5d | -11.22% | -10.65% | -0.56% | 0.90 | No |
| 2.0x | 10d | -2.83% | -15.50% | +12.67% | 0.16 | No |

The straddle loses money in absolute terms in every single cell (win
rates 16-30%) -- theta decay plus the stated cost assumption dominate.
One variant (1.5x/10d) shows a raw p=0.021 relative improvement over
baseline, but the adjacent 5-day version of the exact same trigger shows
nothing (p=0.49) -- inconsistent behavior across horizons that should
move together if the effect were real, and it does not survive
Bonferroni or BH across the 4 variants regardless.

### Not chased, logged for later if ever revisited
A cheaper structure (strangle instead of straddle), a tighter cost
assumption using the real measured 0.46% SPX call spread instead of the
conservative 4%/leg padding, a holding period more precisely matched to
avoid excess unused time value, or expirations chosen per-horizon instead
of a single fixed 10-day-minimum contract marked at two points. Any of
these could plausibly change the number -- which is exactly why none are
being tried now, after seeing this result.
