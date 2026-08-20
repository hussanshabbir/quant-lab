# Out-of-sample data split (locked 2026-08-15)

Per blueprint Phase 65, confirmed with the user in chat before Phase 54 ran.
Enforced in code by `src/research/data_split.py` — this document records the
decision; that module is the actual guard.

## The three buckets

Computed against `data/raw/es_futures/session_labels.parquet` (3,614 distinct
labeled trading dates, 2010-06-07 through 2026-08-14). Boundaries are
calendar-year cuts (end of 2021 / end of 2023) snapped to the nearest real
trading date on each side.

| Bucket | Date range | Trading dates | Labeled rows (both comparisons) |
|---|---|---|---|
| **DISCOVERY** | 2010-06-07 → 2021-12-31 | 2,421 | 4,831 |
| **VALIDATION** | 2022-01-03 → 2023-12-29 | 516 | 1,031 |
| **LOCKED TEST** | 2024-01-02 → 2026-08-14 | 677 | 1,352 |

Sum checks out exactly: 2,421 + 516 + 677 = 3,614.

## Rules

1. **Phase 54 (H001–H012) and all hypothesis-discovery work runs on DISCOVERY
   only.** No exceptions without a recorded decision to change this document.
2. **VALIDATION** exists for iterating on hypothesis definitions, checking
   robustness, and adjusting methodology — without touching LOCKED TEST.
3. **LOCKED TEST is not opened implicitly.** Finishing discovery/validation
   iteration, feeling confident, or running out of other things to try does
   NOT authorize opening it. The only path to it in code is
   `data_split.locked_test_slice(df, confirmed_by="<name>")` — the
   `confirmed_by` argument is keyword-only with no default, so calling it
   without an explicit name is a `TypeError`, and calling it with an empty
   name raises `LockedTestAccessError`. If any code path ever reads locked
   data without that explicit call, treat it as a bug and stop immediately
   — not as a shortcut worth keeping.
4. **Opening LOCKED TEST requires the user's explicit, deliberate
   confirmation by name**, given at the time it's actually needed (i.e. when
   a specific surviving hypothesis is ready for final out-of-sample
   confirmation) — not a standing blanket approval given now.

## Why these boundaries, not others

The user's original instruction (this conversation, 2026-08-15) asked for
the blueprint's actual 3-way DISCOVERY → VALIDATION → LOCKED TEST structure
(Phase 65's own illustrative example: "DISCOVERY 2008-2021, VALIDATION
2022-2024, LOCKED TEST 2025-2026"), rather than a simpler 2-way split. The
boundaries here match that structure as closely as the real data allows:
discovery ends 2021, validation covers 2022–2023, locked test covers
2024 onward through the actual end of the real data (2026-08-14) — a bit
further than "2024–2026" reads literally, since our real pulled data
extends into August 2026, not just through calendar 2026.

Context noted at confirmation time: 2010–2015 has materially more data-
quality gaps (missing sessions from real feed gaps, a filtered class of
settlement-artifact bars — see `docs/known_gaps.md` Gaps 3 and 5) than
2016+. All of that is already handled (filtered bars documented and
excluded; missing sessions correctly absent rather than fabricated) before
this split was drawn — it was not a reason to exclude 2010–2015 from
DISCOVERY, since discovery benefits from more data and the known issues are
already accounted for upstream.
