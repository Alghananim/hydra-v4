"""HYDRA V4 — Historical event calendar for replay (root-cause solution).

Provides deterministic (event_id, scheduled_utc) tuples for the
curated 10-event set defined in config/news/events.yaml.

Sources of truth for dates:
  * FOMC decisions   — Fed publishes full-year schedule in July prior
  * FOMC minutes     — released exactly 3 weeks (21 days) after each decision
  * ECB decisions    — ECB publishes full-year schedule in advance
  * BoJ decisions    — BoJ publishes annual MPM schedule
  * US NFP           — first Friday of each month (rule-based)
  * US CPI           — ~13th of each month, BLS schedule (push to next weekday)
  * US GDP Advance   — quarterly (Jan/Apr/Jul/Oct ~30th, push to weekday)
  * Powell speech    — pinned to FOMC press conference (30min after decision)
  * Lagarde speech   — pinned to ECB press conference (45min after decision)
  * Ueda speech      — pinned to BoJ press conference

Hard rules:
  * NO NETWORK calls anywhere.
  * Times converted from local-bank wall-clock via zoneinfo (DST-safe).
  * NO LOOKAHEAD: every date here was publicly known well before
    the event. Replay engine still gates by start_utc <= scheduled_utc <= end_utc.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Tuple
from zoneinfo import ZoneInfo

# Time zones — bank-local wall-clock for each event class
_NY = ZoneInfo("America/New_York")     # Fed, BLS, BEA all release on NY clock
_FRANKFURT = ZoneInfo("Europe/Berlin")  # ECB / Lagarde
_TOKYO = ZoneInfo("Asia/Tokyo")         # BoJ / Ueda


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _at_local(d: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    """Convert a local wall-clock (date, hour, minute, tz) to UTC. DST-safe."""
    local = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
    return local.astimezone(timezone.utc)


def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    # Python: Monday=0..Sunday=6; Friday=4
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _push_to_weekday(d: date) -> date:
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------------
# Hardcoded actual decision dates (publicly published, no lookahead)
# ---------------------------------------------------------------------

# FOMC decisions — day 2 of each 2-day meeting; press release 14:00 ET
_FOMC_DECISION_DATES: List[date] = [
    # 2024
    date(2024, 1, 31), date(2024, 3, 20), date(2024, 5, 1),
    date(2024, 6, 12), date(2024, 7, 31), date(2024, 9, 18),
    date(2024, 11, 7), date(2024, 12, 18),
    # 2025
    date(2025, 1, 29), date(2025, 3, 19), date(2025, 5, 7),
    date(2025, 6, 18), date(2025, 7, 30), date(2025, 9, 17),
    date(2025, 10, 29), date(2025, 12, 10),
    # 2026 (announced in advance per Fed convention)
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
]

# ECB decisions — typically Thursdays, 13:45 CET (Frankfurt)
# 2024-2026 ECB Governing Council monetary policy meeting dates
_ECB_DECISION_DATES: List[date] = [
    # 2024
    date(2024, 1, 25), date(2024, 3, 7), date(2024, 4, 11),
    date(2024, 6, 6), date(2024, 7, 18), date(2024, 9, 12),
    date(2024, 10, 17), date(2024, 12, 12),
    # 2025
    date(2025, 1, 30), date(2025, 3, 6), date(2025, 4, 17),
    date(2025, 6, 5), date(2025, 7, 24), date(2025, 9, 11),
    date(2025, 10, 30), date(2025, 12, 18),
    # 2026
    date(2026, 1, 22), date(2026, 3, 5), date(2026, 4, 16),
]

# BoJ Monetary Policy Meeting — decision typically released ~12:00 JST
_BOJ_DECISION_DATES: List[date] = [
    # 2024
    date(2024, 1, 23), date(2024, 3, 19), date(2024, 4, 26),
    date(2024, 6, 14), date(2024, 7, 31), date(2024, 9, 20),
    date(2024, 10, 31), date(2024, 12, 19),
    # 2025
    date(2025, 1, 24), date(2025, 3, 19), date(2025, 5, 1),
    date(2025, 6, 17), date(2025, 7, 31), date(2025, 9, 19),
    date(2025, 10, 30), date(2025, 12, 18),
    # 2026
    date(2026, 1, 23), date(2026, 3, 18), date(2026, 4, 28),
]


def _fomc_minutes_dates() -> List[date]:
    """Minutes are released 3 weeks (21 days) after each FOMC decision."""
    return [d + timedelta(days=21) for d in _FOMC_DECISION_DATES]


def _nfp_dates(start: date, end: date) -> List[date]:
    """First Friday of each month — US NFP release."""
    out: List[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        d = _first_friday(y, m)
        if start <= d <= end:
            out.append(d)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _cpi_dates(start: date, end: date) -> List[date]:
    """US CPI — ~13th of each month, pushed to next weekday."""
    out: List[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        d = _push_to_weekday(date(y, m, 13))
        if start <= d <= end:
            out.append(d)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _gdp_advance_dates(start: date, end: date) -> List[date]:
    """US GDP Advance — quarterly, ~30th of Jan/Apr/Jul/Oct."""
    out: List[date] = []
    for y in range(start.year - 1, end.year + 2):
        for m in (1, 4, 7, 10):
            d = _push_to_weekday(date(y, m, 30))
            if start <= d <= end:
                out.append(d)
    return out


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def build_replay_occurrences(
    start_utc: datetime,
    end_utc: datetime,
) -> List[Tuple[str, datetime]]:
    """Build (event_id, scheduled_utc) tuples for the replay window.

    The returned list is sorted by scheduled_utc and contains ONLY events
    that fall strictly within [start_utc, end_utc]. Caller passes this to
    EventScheduler.load_occurrences().
    """
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("start_utc and end_utc must be tz-aware UTC")

    out: List[Tuple[str, datetime]] = []
    s_d, e_d = start_utc.date(), end_utc.date() + timedelta(days=1)

    # FOMC decision @ 14:00 ET
    for d in _FOMC_DECISION_DATES:
        if s_d <= d <= e_d:
            out.append(("us_fomc_decision", _at_local(d, 14, 0, _NY)))
            # Powell press conference 30min later
            out.append(("us_powell_speech", _at_local(d, 14, 30, _NY)))

    # FOMC minutes @ 14:00 ET, 3 weeks after each decision
    for d in _fomc_minutes_dates():
        if s_d <= d <= e_d:
            out.append(("us_fomc_minutes", _at_local(d, 14, 0, _NY)))

    # ECB decision @ 13:45 CET; Lagarde press conf @ 14:30 CET
    for d in _ECB_DECISION_DATES:
        if s_d <= d <= e_d:
            out.append(("eu_ecb_decision", _at_local(d, 13, 45, _FRANKFURT)))
            out.append(("eu_lagarde_speech", _at_local(d, 14, 30, _FRANKFURT)))

    # BoJ decision @ 12:00 JST; Ueda press conf @ 15:30 JST
    for d in _BOJ_DECISION_DATES:
        if s_d <= d <= e_d:
            out.append(("jp_boj_decision", _at_local(d, 12, 0, _TOKYO)))
            out.append(("jp_ueda_speech", _at_local(d, 15, 30, _TOKYO)))

    # US NFP @ 8:30 ET, first Friday
    for d in _nfp_dates(s_d, e_d):
        out.append(("us_nfp", _at_local(d, 8, 30, _NY)))

    # US CPI @ 8:30 ET, ~13th
    for d in _cpi_dates(s_d, e_d):
        out.append(("us_cpi", _at_local(d, 8, 30, _NY)))

    # US GDP Advance @ 8:30 ET, quarterly
    for d in _gdp_advance_dates(s_d, e_d):
        out.append(("us_gdp_advance", _at_local(d, 8, 30, _NY)))

    # Filter strictly to UTC window, then sort
    out = [(eid, t) for (eid, t) in out if start_utc <= t <= end_utc]
    out.sort(key=lambda x: x[1])
    return out
