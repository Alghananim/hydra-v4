"""GateMind V4 — New York session check (DST-aware via zoneinfo).

Two LOCAL NY windows: 03:00-05:00 and 08:00-12:00. End is exclusive of the
top-of-hour boundary (i.e. 05:00 sharp is OUT, 04:59:59 is IN).

DST is handled automatically by zoneinfo("America/New_York"): a UTC instant
is converted to NY local time and the hour gate is applied. The "spring
forward" hour (02:00-03:00 NY) does not exist — UTC inputs that would map
into that gap are rejected as `outside_window`. The "fall back" hour
(01:00-02:00 NY) repeats — both occurrences are correctly mapped because
zoneinfo preserves UTC offset on conversion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from gatemind.v4.gatemind_constants import (
    DEFAULT_SESSION_WINDOWS_UTC,
    NY_TIMEZONE,
    NY_WINDOWS,
    OUTSIDE_WINDOW_LABEL,
    SESSION_WINDOWS_UTC,
    WINDOW_LABELS,
)

_NY_TZ = ZoneInfo(NY_TIMEZONE)


def to_ny(now_utc: datetime) -> datetime:
    """Convert tz-aware UTC to America/New_York local."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be tz-aware (UTC)")
    return now_utc.astimezone(_NY_TZ)


def _is_weekend_utc(now_utc: datetime) -> bool:
    """Forex weekend: Fri 21:00 UTC → Sun 22:00 UTC."""
    wd, h = now_utc.weekday(), now_utc.hour
    if wd == 4 and h >= 21:
        return True
    if wd == 5:
        return True
    if wd == 6 and h < 22:
        return True
    return False


def is_in_session(now_utc: datetime, pair: str = "") -> Tuple[bool, str]:
    """V12-F3: per-pair UTC session check.

    EUR_USD : London (07-13) + NY (13-21).
    USD_JPY : Tokyo (00-07) + London_NY (12-21).
    Other   : NY legacy (12-21).
    Plus weekend cut (Fri 21:00 → Sun 22:00 UTC).
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be tz-aware (UTC)")
    if _is_weekend_utc(now_utc):
        return False, "outside_window_weekend"
    h = now_utc.hour
    windows = SESSION_WINDOWS_UTC.get(pair) or DEFAULT_SESSION_WINDOWS_UTC
    for label, start, end in windows:
        if start <= h < end:
            return True, f"in_window_{label}"
    return False, OUTSIDE_WINDOW_LABEL


def is_in_ny_window(now_utc: datetime) -> Tuple[bool, str]:
    """Legacy NY-local-time check kept for backwards compat with tests
    and any code path that does not have a pair handle. Production
    flow goes through is_in_session(now_utc, pair) instead.
    """
    ny = to_ny(now_utc)
    hour = ny.hour
    for window in NY_WINDOWS:
        start, end = window
        if start <= hour < end:
            return True, WINDOW_LABELS.get(window, "in_window_unknown")
    return False, OUTSIDE_WINDOW_LABEL


def session_status(now_utc: datetime, pair: str = "") -> str:
    """Convenience — return the label only. Uses V12 per-pair check
    when pair is given, otherwise NY-legacy."""
    if pair:
        _, label = is_in_session(now_utc, pair)
    else:
        _, label = is_in_ny_window(now_utc)
    return label
