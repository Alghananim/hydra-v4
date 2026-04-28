"""HYDRA V11 — trading window schedule.

V5's two NY windows (03-05 and 08-12 NY local = 6h/day) excluded ~75 %
of the M15 timeline. V11 expands to 4 windows that align with major
session opens/closes. Goal: 10h/day in-window time.

All times in UTC for backtest determinism. Live runtime converts via
zoneinfo.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple


# Each window is (start_hour_utc, end_hour_utc, label).
# DST-agnostic UTC bounds. The orchestrator converts to NY local for
# the user's reporting only.
TRADING_WINDOWS: Tuple[Tuple[int, int, str], ...] = (
    (0, 2, "asian_open"),         # JPY/AUD pair activity
    (7, 9, "london_open"),         # EUR/GBP pair activity (London + NY pre-open overlap)
    (12, 16, "london_ny_overlap"), # PEAK liquidity — all majors active
    (19, 21, "ny_close"),          # USD pair activity wind-down
)
# Total: 2 + 2 + 4 + 2 = 10 hours / 24 = 41.7 % of timeline (vs V5's 25 %).


def is_in_any_window(now_utc: datetime) -> Tuple[bool, str]:
    """Return (in_window, label). label is 'outside_window' if not in any."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be tz-aware UTC")
    h = now_utc.astimezone(timezone.utc).hour
    for lo, hi, label in TRADING_WINDOWS:
        if lo <= h < hi:
            return True, label
    return False, "outside_window"


def hours_per_day() -> int:
    return sum(hi - lo for lo, hi, _ in TRADING_WINDOWS)


def coverage_pct() -> float:
    return hours_per_day() / 24.0 * 100.0
