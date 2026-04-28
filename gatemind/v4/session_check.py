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
    NY_TIMEZONE,
    NY_WINDOWS,
    OUTSIDE_WINDOW_LABEL,
    WINDOW_LABELS,
)

_NY_TZ = ZoneInfo(NY_TIMEZONE)


def to_ny(now_utc: datetime) -> datetime:
    """Convert tz-aware UTC to America/New_York local."""
    if now_utc.tzinfo is None:
        # Be paranoid: reject naive datetimes — caller must hand us tz-aware.
        raise ValueError("now_utc must be tz-aware (UTC)")
    return now_utc.astimezone(_NY_TZ)


def is_in_ny_window(now_utc: datetime) -> Tuple[bool, str]:
    """Return (in_window, label).

    label is one of:
      "in_window_pre_open"   - 03:00 to 04:59:59 NY local
      "in_window_morning"    - 08:00 to 11:59:59 NY local
      "outside_window"       - everything else
    """
    ny = to_ny(now_utc)
    hour = ny.hour
    for window in NY_WINDOWS:
        start, end = window
        if start <= hour < end:
            return True, WINDOW_LABELS.get(window, "in_window_unknown")
    return False, OUTSIDE_WINDOW_LABEL


def session_status(now_utc: datetime) -> str:
    """Convenience — return the label only."""
    _, label = is_in_ny_window(now_utc)
    return label
