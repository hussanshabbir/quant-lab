"""Asia / Europe / New York session construction for R001 (Phase 49).

This is the session engine referenced in blueprint Phase 5 ("time /
session / contract engine") and used concretely by Phase 49 ("session
construction: for each trading day, build Asia/Europe/New York sessions
with exchange-calendar-aware timestamps").

WHAT A "SESSION" MEANS HERE
----------------------------
ES trades on a single, nearly-continuous CME Globex market -- there is
no separate "Asian ES market" the way there is a separate JPX or HKEX.
So "Asia session", "Europe session", and "New York session" are not
different markets; they are three fixed local-wall-clock windows,
carved out of one continuous Globex trading day, using the regular cash
market hours of a representative hub exchange for each region:

    Asia      -> Asia/Tokyo    09:00-15:00 (JPX cash equity hours)
    Europe    -> Europe/London 08:00-16:30 (LSE cash equity hours)
    New York  -> America/New_York 09:30-16:00 (NYSE cash equity / CME ES RTH)

This is a deliberate, documented research choice (Phase 49/51 needs
consistent Asia-high/Europe-high/NY-high definitions for H001-H012), not
a universal truth -- it does NOT model JPX's morning/afternoon split
with a lunch break, JPX day/night sessions, HKEX's three-part day, or
LSE/HKEX/JPX auction periods (those are Phase 16/17 concerns). It is
the simplest defensible partition of the ES trading day into three
audit-able regional windows and should be reviewed as a research
parameter, not treated as fixed infrastructure.

Because all three reference hours are the *cash equity* hours of their
hub exchange, and because Tokyo is far enough ahead of UTC that its
local calendar date equals the UTC calendar date during its session,
all three sessions for CME trading date D use the SAME calendar date D
in each session's own local timezone -- there is no date-shifting
arithmetic needed. In UTC, this naturally produces:

    Asia    ~00:00-06:00 UTC
    Europe  ~07:00-16:30 UTC (exact bounds shift with UK DST)
    New York ~13:30-21:00 UTC (exact bounds shift with US DST)

Note Europe's close and New York's open overlap in UTC -- that overlap
is real (the "London/New York overlap"), not a bug.

DST HANDLING -- WHY THIS IS NOT A FIXED UTC OFFSET PROBLEM
------------------------------------------------------------
The three reference timezones do not change clocks in sync:

  * Asia/Tokyo observes NO daylight saving time (Japan abolished DST in
    1951). Its UTC offset is a constant +09:00, year round. Hong Kong
    and Singapore likewise observe no DST.
  * Europe/London observes British Summer Time (BST, UTC+1) from the
    last Sunday in March to the last Sunday in October, and GMT
    (UTC+0) otherwise.
  * America/New_York observes Eastern Daylight Time (EDT, UTC-4) from
    the second Sunday in March to the first Sunday in November, and
    EST (UTC-5) otherwise.

Because the US and UK/EU switch on DIFFERENT dates (roughly 1-3 weeks
apart in both spring and autumn), the London-New York UTC offset is NOT
a constant "5 hours" year-round -- for a short window each spring
(after the US has sprung forward but before the UK has) and each
autumn (after the UK has fallen back but before the US has), the
offset compresses to 4 hours. This module does not special-case that:
each session's local open/close is built directly from that session's
OWN ``zoneinfo`` timezone (which has the IANA tzdata transition rules
built in) and converted to UTC independently. There is no shared "US
DST offset" applied to the Europe or Asia session -- correctness here
comes from using three independent zoneinfo conversions, not from one
central DST rule. See ``tests/test_sessions.py`` for a worked example
across a US-only DST transition.

CME HOLIDAYS AND EARLY CLOSES
-------------------------------
Session windows are clipped to the actual CME Globex open/close bounds
for that trading date (see ``exchange.CMEEquityCalendar``). On a full
CME holiday there is no session data at all -- ``build_day_sessions``
returns None. On an early-close day (e.g. the day before Thanksgiving),
the New York session's nominal 09:30-16:00 window is clipped to
whatever CME's actual early close was; this is flagged via
``SessionWindow.was_clipped``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pandas as pd

from .exchange import UTC, CMEEquityCalendar

UTC = UTC  # re-exported for convenience


@dataclass(frozen=True)
class SessionDefinition:
    """A region's session expressed as local wall-clock start/end times."""

    name: str
    tz_name: str
    local_start: dt.time
    local_end: dt.time


# Ordered so that, for a normal (non-clipped) trading day, iterating
# this dict yields sessions in chronological UTC order.
SESSION_DEFINITIONS: dict[str, SessionDefinition] = {
    "asia": SessionDefinition(
        name="asia",
        tz_name="Asia/Tokyo",
        local_start=dt.time(9, 0),
        local_end=dt.time(15, 0),
    ),
    "europe": SessionDefinition(
        name="europe",
        tz_name="Europe/London",
        local_start=dt.time(8, 0),
        local_end=dt.time(16, 30),
    ),
    "new_york": SessionDefinition(
        name="new_york",
        tz_name="America/New_York",
        local_start=dt.time(9, 30),
        local_end=dt.time(16, 0),
    ),
}


@dataclass(frozen=True)
class SessionWindow:
    """One region's session on one CME trading date, in local and UTC time."""

    name: str
    trading_date: dt.date
    tz_name: str
    local_open: dt.datetime
    local_close: dt.datetime
    utc_open: pd.Timestamp
    utc_close: pd.Timestamp
    was_clipped: bool
    clip_reason: str | None


def _localize(trading_date: dt.date, local_time: dt.time, tz_name: str) -> dt.datetime:
    """Combine a calendar date and wall-clock time into a zoneinfo-aware datetime.

    Using ``ZoneInfo`` (rather than a fixed ``timedelta`` offset) is
    what makes this DST-correct: the same code path handles Asia/Tokyo
    (no DST), Europe/London (BST/GMT), and America/New_York (EDT/EST)
    correctly, because the offset lookup is delegated to the IANA tzdata
    rules for that specific zone and date rather than assumed.
    """
    return dt.datetime.combine(trading_date, local_time, tzinfo=ZoneInfo(tz_name))


def build_day_sessions(
    trading_date: dt.date,
    calendar: CMEEquityCalendar,
) -> dict[str, SessionWindow] | None:
    """Build Asia/Europe/New York session windows for one CME trading date.

    Returns None if ``trading_date`` is a full CME holiday (no Globex
    trading occurs at all). Otherwise returns a dict keyed by session
    name ("asia", "europe", "new_york"), each clipped to the actual
    Globex open/close bounds for that date -- relevant on early-close
    days, where the New York session in particular may close before its
    nominal 16:00 local end.
    """
    globex_day = calendar.trading_day_bounds(trading_date)
    if globex_day is None:
        return None

    sessions: dict[str, SessionWindow] = {}
    for sess_def in SESSION_DEFINITIONS.values():
        local_open = _localize(trading_date, sess_def.local_start, sess_def.tz_name)
        local_close = _localize(trading_date, sess_def.local_end, sess_def.tz_name)
        utc_open = pd.Timestamp(local_open).tz_convert(UTC)
        utc_close = pd.Timestamp(local_close).tz_convert(UTC)

        was_clipped = False
        clip_reason = None

        if utc_open < globex_day.open_utc:
            utc_open = globex_day.open_utc
            was_clipped = True
            clip_reason = "clipped_to_globex_open"
        if utc_close > globex_day.close_utc:
            utc_close = globex_day.close_utc
            was_clipped = True
            clip_reason = (
                "clipped_to_globex_early_close"
                if globex_day.is_early_close
                else "clipped_to_globex_close"
            )

        sessions[sess_def.name] = SessionWindow(
            name=sess_def.name,
            trading_date=trading_date,
            tz_name=sess_def.tz_name,
            local_open=local_open,
            local_close=local_close,
            utc_open=utc_open,
            utc_close=utc_close,
            was_clipped=was_clipped,
            clip_reason=clip_reason,
        )

    return sessions
