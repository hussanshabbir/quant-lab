# Known gaps in the calendar/session engine (src/calendar/)

This file exists because of blueprint Phase 86 (research governance): known
defects and deferred decisions must be permanently recorded, not silently
carried in someone's head. Each entry below has an explicit trigger
condition for when it must be revisited -- don't let these get lost as the
project goes deeper into the phase map.

## Gap 1 -- `CME_Equity` misses ad hoc CME special closures (deferred)

**What's wrong:** `pandas_market_calendars`'s `CME_Equity` calendar (the
calendar `src/calendar/exchange.py`'s `CMEEquityCalendar` wraps) correctly
encodes CME's *recurring* holiday/early-close rules, but has at least one
confirmed gap on a *one-off* ad hoc closure announced via a CME Special
Executive Report rather than a standing rule.

Confirmed instance: **2025-01-09**, the U.S. National Day of Mourning for
former President Jimmy Carter. Per CME Group's own press release, CME
equity-index Globex products (ES included) traded overnight as normal and
closed early at 08:30 CT that day, then reopened at the regular 17:00 CT
open for the next trading date. Real trading happened.

`CMEEquityCalendar.is_trading_day(date(2025, 1, 9))` currently returns
`False`, and `trading_day_bounds(...)` returns `None` -- i.e. the library
treats it as a full holiday with zero trading, which is incorrect. Any
session construction touching this date will silently produce no session
data at all for a day that actually has a (shortened) real session.

This behavior is intentionally pinned by
`tests/test_known_gaps.py::test_jan_9_2025_ad_hoc_closure_is_a_known_library_gap`
so a future `pandas_market_calendars` upgrade that fixes it will fail that
test loudly rather than the fix going unnoticed.

**Why we're deferring:** this is a single known date so far, with no live
impact yet (no data has been ingested). Building a general-purpose ad hoc
override mechanism now, before we know how many such dates exist across
the actual study period (2008+) or what source will systematically surface
them (CME's Special Executive Report archive), risks a bespoke,
under-specified layer. This is better scoped together with Phase 48's
contract-master work, which also needs a place for hand-verified reference
data overrides.

**Trigger to revisit (do not skip past this):** before trusting any
session or statistical result (Phase 55+) that touches 2025-01-09
specifically, OR before any broader audit of "how many ad hoc CME special
closures exist in our study period" -- build a small `known_overrides.py`
in `src/calendar/`, keyed by date, sourced from CME's own Special
Executive Report archive, and wire it into `CMEEquityCalendar` so it
overrides the underlying library's answer for those specific dates.

## Gap 2 -- two different CME equity calendars exist in the library; we use `CME_Equity`, not `CME Globex Equity`

**What's going on:** `pandas_market_calendars` ships two distinct CME
equity-index calendar implementations:

- `CME_Equity` (class `CMEEquityExchangeCalendar`) -- what this project
  uses. Correctly models the actual 2005-09 to 2012-11 period when CME
  Globex equity-index hours were genuinely shorter (open 15:30 CT, close
  15:15 CT, not today's 17:00/16:00), and models the daily 15:15-15:30 CT
  maintenance break via `break_start`/`break_end` columns.
- `CME Globex Equity` (class `CMEGlobexEquitiesExchangeCalendar`) -- not
  used here. Applies today's 17:00/16:00 CT hours retroactively to all of
  history (wrong for 2005-2012), and does not model the daily maintenance
  break at all (no break columns in its schedule output).

Since the blueprint's own out-of-sample plan (Phase 65) proposes a
discovery window starting 2008, the 2005-2012 hours regime is directly
relevant, which is why `CME_Equity` is the correct choice between the two.
This behavior is pinned by
`tests/test_known_gaps.py::test_2005_2012_hours_regime_is_correctly_modeled`.

**Why this is listed as a gap rather than just a settled decision:** it's
easy, months from now, to reach for "the CME Globex calendar" by name and
grab `CME Globex Equity` instead, silently reintroducing the 2005-2012
hours bug. Recording the decision here is the guard against that.

**Trigger to revisit:** before running any statistical analysis (Phase
55+) on a date range touching 2005-2012, confirm `CMEEquityCalendar` is
still backed by `CME_Equity` (not `CME Globex Equity`). If a future change
switches the backing calendar, the hours-regime override needs to be
rebuilt by hand for that period.

## Gap 3 -- corrupted bars in the real GLBX.MDP3 ohlcv-1m pull (2010-2015 vintage), now filtered

**What's wrong:** Phase 47 validation against the real 67-contract pull
(`data/raw/es_futures/ohlcv_1m/`) surfaced two distinct, evidence-verified
categories of bars that are not real 1-minute trading data, both confined
almost entirely to 2010-2015-vintage contracts:

1. **`session_settlement_summary_bar`** (590 bars): a single bar -- almost
   always timestamped exactly `23:59:00 UTC`, occasionally near a contract's
   own regular session close -- whose volume exceeds the SUM of every other
   real bar in its own correctly-attributed CME trading date, AND whose
   high/low falls outside the range everything else that date actually
   traded. Both conditions are physically impossible for a genuine single
   real trading minute. Worst confirmed example: `ESU11 2011-08-09 23:59:00
   UTC`, volume 6,223,210 against a real trading-date total of 25,368 (245x)
   -- during the real Aug 2011 US credit-downgrade crisis week, whose
   genuinely elevated but real volume for this back-month contract that day
   was fully captured in the other 127 real bars, topping out at 1,502 in
   any actual minute. Likely a session/settlement summary record from
   Databento's historical reconstruction for this vintage, mislabeled as a
   single 1-minute bar. Affects 33 distinct contracts, entirely ESH10
   through ESZ15/ESH16 (contract-expiry years 2010-2015); no confirmed
   instance in 2016+ contracts under this test.

2. **`post_expiration_isolated_settlement_print`** (11 bars): exactly one
   per affected contract, on that contract's own actual `last_trade_date`,
   isolated by a 1223-1352 minute (~20-22.5 hour) gap from the prior real
   bar -- i.e. within the same trading week, well after the documented 8:30
   CT SOQ real-trading cutoff (`calendar/contracts.py`'s `_SOQ_TERMINATION_LOCAL`)
   -- with volume 16,646-48,489 (170-450x that contract's own lifetime
   median 1-minute volume). Affects: ESH11, ESH12, ESM10, ESM11, ESM12,
   ESU10, ESU11, ESZ10, ESZ11, ESZ13, ESZ14.

**What was explicitly NOT filtered, and why this matters:** a naive
volume-magnitude-only test was tried first and rejected because it caught
real data -- specifically month-end index-rebalancing volume spikes (e.g.
`ESM21 2021-03-31 19:59 UTC` at 151,402, `ESM22 2022-03-31` at 162,692),
which are large but stay within the real day's traded price range and
don't exceed the rest of the day's real volume combined. 27 such bars were
identified as elevated-but-ambiguous and deliberately excluded from
filtering -- see `n_excluded_ambiguous_not_filtered` in
`data/raw/es_futures/known_bad_bars.json`. Two boundary-minute bars
(`ESM18 2018-06-15 13:30:00`, `ESM23 2023-06-16 13:30:00`, volume 1 and 6)
were also examined and left alone -- they're just the last few seconds of
real trading landing exactly on the SOQ-termination-labeled minute, not
corrupted data.

**Where the fix lives:** `src/ingest/detect_bad_bars.py` regenerates
`data/raw/es_futures/known_bad_bars.json` (the exact symbol+timestamp
exclusion list, reproducible from code, not hand-maintained) and exposes
`filter_known_bad_bars(df, symbol)` for downstream phases to call. Applied
before Phase 48 roll-detection (which compares daily volume between
adjacent contracts, and would have had its roll dates badly distorted by a
6.2-million-contract phantom spike) and should be applied before any other
volume- or price-extreme-sensitive real-data work.

**Trigger to revisit:** if 2016+ contracts start showing confirmed
instances under this test (none seen as of this writing), or if the 27
ambiguous bars need a real decision (e.g. because one turns out to matter
for a specific hypothesis test in Phase 54) rather than sitting unfiltered.

## Gap 4 -- CME ad hoc closures not modeled by `CME_Equity`, second confirmed instance

**What's wrong:** Gap 1 already documents that `CME_Equity` incorrectly
treats `2025-01-09` (Jimmy Carter National Day of Mourning) as a full
holiday when real (shortened) trading occurred. Phase 47 validation against
real data confirms that exact predicted failure mode -- 2,345 bars across
several contracts on `2025-01-08`/`2025-01-09` were flagged by
`check_bars_outside_globex_hours` because the library doesn't recognize
those hours as a valid session.

It also surfaces a **second, previously undocumented instance of the same
category of gap**: `2018-12-04`/`2018-12-05` (George H.W. Bush National Day
of Mourning). Real trades exist in the actual data for both dates that
`CMEEquityCalendar` doesn't recognize as valid session time.

**Important distinction from Gap 3:** these are REAL trades, not corrupted
data. They must NOT be filtered/removed -- the fix is to correct the
calendar's session recognition, not discard real market data.

**Trigger to revisit:** before trusting any session or statistical result
(Phase 55+) that touches `2018-12-04`, `2018-12-05`, `2025-01-08`, or
`2025-01-09` specifically -- per Gap 1's already-planned fix, build
`known_overrides.py` in `src/calendar/`, keyed by date and sourced from
CME's Special Executive Report archive, covering both incidents together.

## Gap 5 -- roll-date detection: real-data validation and the majority-fallback rule

**What was found (Phase 48, 2026-08):** `roll.py`'s `volume_crossover_roll_date`
was previously only tested against synthetic fixtures. Applied to real
per-contract daily volume (67 contracts, Gap 3's known-bad bars already
filtered out) with its defaults (`confirm_days=1`, no window restriction),
54 of 66 real front/next transitions produced nonsensical roll dates --
median 290 days before the front contract's expiry, some earlier than the
front contract was even meaningfully listed. Root cause, confirmed by hand
(e.g. `ESZ10`/`ESH11` on 2010-06-10: volumes of 1 and 2 contracts): deep in
a contract's thin back-month history, single-day volume noise trivially
produces a "crossover" many months before any real migration, and
`confirm_days=1` accepts it immediately.

**Fix:** bound the crossover search to the 200 days before the front
contract's own `last_trade_date` (excludes the noise regime), and use
`confirm_days=5` (requires a sustained shift, not one lucky/unlucky day).
Tested `confirm_days` at 1/5/10/20 against all 66 real transitions -- 5 is
the validated value; 10+ fails entirely because even genuine migration
periods have occasional single-day dips that break a longer strict streak.
With this configuration, 61 of 66 transitions resolve cleanly, tightly
clustered 4-8 days before expiry (mean 5.75, std 1.5, zero outliers) --
consistent with known real-world ES roll conventions.

**The remaining 3** (`ESZ10->ESH11`, `ESZ11->ESH12`, `ESH12->ESM12`, all
2010-2012 vintage) showed a real, visible migration 8-11 trading days
before expiry that failed only because a single near-tie day or a
front-contract last-day settlement-related volume blip broke the streak
into pieces each shorter than 5. Rather than hand-pick these 3 dates,
`majority_crossover_roll_date` (window_days=8, needs a majority i.e. >=5 of
8, not all 8) was added as a documented, reproducible fallback -- see its
docstring in `roll.py` for the full rationale -- and wired in uniformly via
`resolve_roll_date` (strict rule first; fallback only fires when the
strict rule returns `None`). Applying the fallback to **all 66**
transitions, not just these 3, was explicitly checked: it never overrides
or changes any of the 61 already-resolved dates (verified computationally,
zero mismatches). The 3 resolve to 11, 14, and 11 days before expiry
respectively -- a little further out than the typical 4-8 day pattern, but
plausible given these are the thinnest-liquidity era in the dataset.

The 2 remaining `None` results (`ESM26->ESU26`, `ESU26->ESZ26`) are
correct, not a gap: `ESU26` is still the actual current front-month
contract as of this writing (2026-08-15), so neither roll has happened
yet.

**Trigger to revisit:** if a future contract transition needs the fallback
and window_days=8 doesn't cleanly resolve it (widen cautiously, re-validate
against all existing transitions the same way, don't just widen and move
on). Also revisit if open-interest data ever gets ingested -- see roll.py's
module docstring on whether volume-crossover is even the best available
signal.
