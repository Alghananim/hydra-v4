"""Retest detection — 3-10 bar window, level ± 0.5×ATR, rejection wick.

RULE 5 (successful retest):
- Within 3..10 bars after a confirmed breakout:
  - touch low/high comes within ± 0.5 × ATR of `level`
  - rejection wick present (wick / range >= RETEST_REJECTION_WICK_MIN)
  - next close beyond level in trend direction
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import (
    RETEST_WINDOW_MIN_BARS,
    RETEST_WINDOW_MAX_BARS,
    RETEST_TOL_ATR,
    RETEST_REJECTION_WICK_MIN,
)


@dataclass
class RetestResult:
    is_retest: bool
    direction: str             # "long" | "short" | "none"
    bar_index: int             # index of the touch bar
    level: float
    reason: str


def _wick_ratio(bar: Bar, side: str) -> float:
    """Rejection wick (long: lower wick / range; short: upper wick / range)."""
    rng = bar.high - bar.low
    if rng <= 0:
        return 0.0
    if side == "long":
        wick = min(bar.open, bar.close) - bar.low
    else:
        wick = bar.high - max(bar.open, bar.close)
    return max(0.0, wick) / rng


def detect_retest(bars: Sequence[Bar],
                  *,
                  breakout_index: int,
                  level: float,
                  atr_value: float,
                  side: str) -> RetestResult:
    """Search for a retest in (breakout_index + 3 .. breakout_index + 10)."""
    if not bars or atr_value <= 0 or side not in ("long", "short"):
        return RetestResult(False, "none", -1, level, "no_inputs")

    n = len(bars)
    lo = breakout_index + RETEST_WINDOW_MIN_BARS
    hi = min(n - 1, breakout_index + RETEST_WINDOW_MAX_BARS)
    if lo >= n:
        return RetestResult(False, side, -1, level, "no_window_yet")

    tol = RETEST_TOL_ATR * atr_value

    for i in range(lo, hi + 1):
        bar = bars[i]
        if side == "long":
            touched = bar.low <= level + tol and bar.low >= level - tol
            wick_ok = _wick_ratio(bar, "long") >= RETEST_REJECTION_WICK_MIN
            cont_ok = (i + 1 < n and bars[i + 1].close > level)
        else:
            touched = bar.high >= level - tol and bar.high <= level + tol
            wick_ok = _wick_ratio(bar, "short") >= RETEST_REJECTION_WICK_MIN
            cont_ok = (i + 1 < n and bars[i + 1].close < level)
        if touched and wick_ok and cont_ok:
            return RetestResult(
                is_retest=True,
                direction=side,
                bar_index=i,
                level=level,
                reason="touch+wick+continuation",
            )

    return RetestResult(False, side, -1, level, "no_qualifying_retest_in_window")
