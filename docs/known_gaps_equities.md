# Known gaps in the equities research line (H015+)

Parallel to `docs/known_gaps.md` (which is scoped to `src/calendar/` and the ES
futures work) -- this file covers gaps specific to equities hypotheses
(H015 onward), per the same blueprint Phase 86 research-governance
principle: known defects and deferred decisions get recorded here, not
silently carried in someone's head.

## Gap 1 -- point-in-time S&P 500 membership is community-sourced, not exchange-certified

**What it is:** H015 (overnight hold effect) needs point-in-time S&P 500
constituent membership to avoid survivorship bias (using today's list
retroactively would silently exclude every company that was removed --
via bankruptcy, decline, acquisition -- inflating historical returns).
The source used is [fja05680/sp500](https://github.com/fja05680/sp500), a
free, actively-maintained CSV of point-in-time membership from 1996
onward.

**Why this is a gap, not just a data source:** it is not exchange-
certified or audited. It's derived from Wikipedia's "Selected Changes to
the list of S&P 500 components" table, which by the maintainer's own
admission is not a complete changes log ("Wikipedia shows 'Selected
Changes' not all changes"), manually cross-referenced against other
sources every couple of months. The repository's own README recommends
purchasing certified data (e.g. Norgate) for rigorous backtesting.

**Why it was accepted anyway:** the maintainer's flagged gaps concentrate
in the pre-2001 era. Databento's equities data (the actual price data
H015 uses) only goes back to 2018-05-01 regardless, so H015's usable
history is already bounded to the more reliable, better-cross-referenced
portion of this source. Accepted with this limitation explicitly
documented, per explicit user approval on 2026-08-21, rather than
silently treated as authoritative.

**Trigger to revisit:** before extending any equities hypothesis's
discovery window earlier than Databento's own 2018-05-01 data start (at
which point the source's pre-2001 gaps would start to matter), or before
treating any H015+ result as strong enough to warrant real capital, at
which point certified point-in-time membership data should be sourced
properly rather than continuing on the community-maintained version.

## Gap 2 -- H015's spread/slippage cost assumption: pre-registered value vs. verified value

Tracked here only until the verification pass (part of H015's own
Phase-67-equivalent cost step) is complete and the real figure is baked
into the trading-sim results directly -- see the H015 report for
whichever of these turns out to be true:

- Pre-registered placeholder (2026-08-21, before verification): 10 bps
  round-trip (5 bps/side), stated explicitly as an assumption requiring
  verification against real quoted-spread data before being used in any
  final reported result -- not a substitute for that verification.
- Verification method: real top-of-book (NBBO) quoted-spread data pulled
  directly from Databento for a representative sample of the actual
  point-in-time universe, not a generic literature citation, mirroring
  how ES's cost assumptions were verified against real CME fee schedules
  rather than left as a stated guess.
- Result (2026-08-21): verified. Real RTH quoted spreads for a 15-stock
  liquid sample: median 4.13 bps, mean 5.45 bps, one-way. The
  pre-registered 10 bps round-trip figure is conservative relative to
  this (not understated), and was kept as-is rather than tightened, since
  the verification sample skews toward mega-caps and the full universe
  includes smaller/less liquid names that plausibly trade wider.

## Gap 3 -- Databento's equities feeds are single-venue, not consolidated; H015 restricted to a decisive-dominance subset

**What's wrong:** `XNAS.ITCH` and `XNYS.PILLAR` (the two long-history
equities datasets used for H015) each reflect only trades EXECUTED ON
THAT ONE EXCHANGE, not the full consolidated national market. In today's
fragmented US equity market, a stock's nominal "primary listing" exchange
often captures well under half of its total national volume. Checked
`DBEQ.BASIC` (Databento's more "consolidated" product) as a possible fix
-- it doesn't solve this either: it returns multiple separate, un-merged
per-sub-venue rows per symbol-day rather than one official print, and it
only covers 2023-03-28 onward regardless (vs. XNAS/XNYS's 2018-05-01).

**Concrete evidence this matters for H015 specifically:** for tickers
where volume splits close to evenly between the two feeds, real OPEN
prices between venues diverge by a median of 24-67 bps and a p95 of
130-308 bps (checked on LIN, CPB, PLTR, KMB) -- larger than the entire
10 bps round-trip cost model, and comparable to or larger than any
plausible overnight effect size. Using either venue's raw print
inconsistently across the ambiguous majority of the universe would inject
venue-selection noise larger than the signal being measured.

**Fix applied, per explicit user decision (2026-08-21):** restrict H015
to the subset of tickers where one venue's volume dominance is decisive,
using a dominance ratio (winning venue's share of the two venues'
combined total volume, summed over the full 2018-2026 pull) computed
BEFORE looking at how many tickers would survive, to avoid picking a
threshold that happens to be convenient:

    THRESHOLD = 0.90 (winner captures >=90% of combined two-venue volume)

**Result: 197 of 702 point-in-time-eligible tickers (28.1%) survive.**
Every single survivor is XNAS.ITCH-dominant -- zero XNYS.PILLAR-dominant
tickers cleared 90%, even though NYSE-listed names obviously exist in the
universe (e.g. BRK.B, correctly XNYS.PILLAR-dominant at 80.5% once the
symbol-format bug below was fixed, but not decisive enough to clear the
threshold). This asymmetry is not fully explained yet -- plausibly
XNAS.ITCH structurally captures a higher share of its own listed names'
total volume than XNYS.PILLAR does of its listed names, but this hasn't
been independently verified and shouldn't be assumed without checking.

**A real bug caught and fixed during this process, recorded for audit:**
`BRK.B` and `BF.B` initially showed ratio=1.0 (100% XNAS, 0% XNYS) purely
because the original XNYS.PILLAR pull used the wrong raw_symbol format
(NYSE Pillar requires a space for share classes -- "BRK B", not "BRK.B";
NASDAQ ITCH's own convention accepts the period form directly, which is
why the XNAS side resolved without incident). This produced a spurious
"decisive" reading for a stock that is, in reality, NYSE-listed. Caught
by checking real historical price levels against known Berkshire
Hathaway Class B prices (consistent -- confirmed the XNAS-side data
itself was real and correctly attributed, just missing its XNYS
counterpart), fixed by re-pulling with the correct symbol format and
recomputing the ratio (BRK.B: 0.805, BF.B: 0.783 -- both correctly
excluded from the decisive universe once fixed).

**Scope limitation this creates, to be stated wherever H015 results are
reported, not just here:** H015 tests the overnight-hold effect on
liquid, NASDAQ-single-venue-dominant large caps specifically -- NOT the
full S&P 500. NYSE-listed and venue-ambiguous names (the majority, 72% of
the point-in-time universe) are excluded entirely, not sampled or
approximated. Any result should be read as applying to this specific
subset, not generalized to "the S&P 500" or "large-cap equities"
broadly without separately re-validating on a properly venue-resolved
NYSE-inclusive universe.

**Trigger to revisit:** before generalizing any H015 finding beyond this
subset, or before extending this line of research to NYSE-listed names --
at which point a genuine primary-listing-exchange reference (not a
volume heuristic) should be sourced, or a true SIP-consolidated data
product should be found, rather than continuing to restrict scope.
