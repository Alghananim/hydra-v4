"""Liquidity sweep / stop-hunt detection.

KEEP from V3 traps (only the working pieces — bull_trap/bear_trap had a
range(i+1, 0) dead loop and are REJECTED).

A liquidity sweep:
  - bar's high pierces an obvious resistance level by some margin AND
  - bar's close is back below that level AND
  - the bar has a long upper wick (>=50% of range)
Mirrored for sweep below support.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import LIQUIDITY_SWEEP_WICK_MIN
from chartmind.v4.models import Level


@dataclass
class SweepResult:
    has_sweep: bool
    direction: str          # "above" (sweep over resistance) | "below" | "none"
    bar_index: int
    level: float
    reason: str


def _upper_wick_ratio(bar: Bar) -> float:
    rng = bar.high - bar.low
    if rng <= 0:
        return 0.0
    return (bar.high - max(bar.open, bar.close)) / rng


def _lower_wick_ratio(bar: Bar) -> float:
    rng = bar.high - bar.low
    if rng <= 0:
        return 0.0
    return (min(bar.open, bar.close) - bar.low) / rng


def detect_recent_sweep(bars: Sequence[Bar],
                        levels: List[Level],
                        *,
                        lookback: int = 5) -> SweepResult:
    """Scan the LAST `lookback` bars for a sweep above any resistance / below any support."""
    if not bars or not levels:
        return SweepResult(False, "none", -1, 0.0, "no_inputs")
    start = max(0, len(bars) - lookback)
    resistances = [L.price for L in levels if L.type == "resistance"]
    supports = [L.price for L in levels if L.type == "support"]
    for i in range(start, len(bars)):
        bar = bars[i]
        # Sweep above
        for r in resistances:
            if bar.high > r and bar.close < r and _upper_wick_ratio(bar) >= LIQUIDITY_SWEEP_WICK_MIN:
                return SweepResult(True, "above", i, r, "high_pierces_close_returns_long_upper_wick")
        for s in supports:
            if bar.low < s and bar.close > s and _lower_wick_ratio(bar) >= LIQUIDITY_SWEEP_WICK_MIN:
                return SweepResult(True, "below", i, s, "low_pierces_close_returns_long_lower_wick")
    return SweepResult(False, "none", -1, 0.0, "no_sweep")
