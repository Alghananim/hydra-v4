"""Pullback detection — depth in [0.5, 1.5] × ATR, HH/HL intact.

RULE 6 (pullback in trend):
- Price retraces between PULLBACK_DEPTH_MIN_ATR and PULLBACK_DEPTH_MAX_ATR
  from the most recent extreme.
- HH/HL structure intact (no break of last opposing swing).
- No opposing breakout occurred since the extreme.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import (
    PULLBACK_DEPTH_MIN_ATR,
    PULLBACK_DEPTH_MAX_ATR,
)
from chartmind.v4.market_structure import Swing, find_swings_adaptive


@dataclass
class PullbackResult:
    is_pullback: bool
    direction: str             # "long" | "short" | "none"
    extreme_index: int
    extreme_price: float
    current_price: float
    depth_atr: float
    reason: str


def _last_swing(swings, kind: str) -> Optional[Swing]:
    for s in reversed(swings):
        if s.kind == kind:
            return s
    return None


def detect_pullback(bars: Sequence[Bar],
                    *,
                    atr_value: float,
                    trend_label: str) -> PullbackResult:
    """Detect a pullback only if trend label is bullish/bearish (strong or weak)."""
    if not bars or atr_value <= 0:
        return PullbackResult(False, "none", -1, 0.0, 0.0, 0.0, "no_inputs")
    if trend_label not in ("bullish_strong", "bullish_weak",
                           "bearish_strong", "bearish_weak"):
        return PullbackResult(False, "none", -1, 0.0, 0.0, 0.0, "no_trend")

    swings = find_swings_adaptive(bars)
    last_close = bars[-1].close

    if trend_label.startswith("bullish"):
        ext = _last_swing(swings, "high")
        opp = _last_swing(swings, "low")
        if ext is None:
            return PullbackResult(False, "long", -1, 0.0, last_close, 0.0, "no_swing_high")
        depth = (ext.price - last_close) / atr_value
        # Structure intact: low has not been breached
        intact = (opp is None) or all(b.low > opp.price for b in bars[opp.index + 1:])
        in_band = PULLBACK_DEPTH_MIN_ATR <= depth <= PULLBACK_DEPTH_MAX_ATR
        if in_band and intact:
            return PullbackResult(
                True, "long", ext.index, ext.price, last_close, depth,
                "depth_in_band_and_structure_intact",
            )
        return PullbackResult(
            False, "long", ext.index, ext.price, last_close, depth,
            f"in_band={in_band} structure_intact={intact}",
        )
    else:
        ext = _last_swing(swings, "low")
        opp = _last_swing(swings, "high")
        if ext is None:
            return PullbackResult(False, "short", -1, 0.0, last_close, 0.0, "no_swing_low")
        depth = (last_close - ext.price) / atr_value
        intact = (opp is None) or all(b.high < opp.price for b in bars[opp.index + 1:])
        in_band = PULLBACK_DEPTH_MIN_ATR <= depth <= PULLBACK_DEPTH_MAX_ATR
        if in_band and intact:
            return PullbackResult(
                True, "short", ext.index, ext.price, last_close, depth,
                "depth_in_band_and_structure_intact",
            )
        return PullbackResult(
            False, "short", ext.index, ext.price, last_close, depth,
            f"in_band={in_band} structure_intact={intact}",
        )
