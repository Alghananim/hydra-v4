"""Candle confirmation — Nison patterns ONLY in-context (≤1.0 × ATR from a level).

KEEP from V3 with strict in-context filter.

We implement the most-cited single-bar / two-bar Nison patterns:
- bullish_engulfing / bearish_engulfing (2-bar)
- hammer / shooting_star            (1-bar)
- pin_bar (long lower wick, body in upper third — bullish reversal)
- piercing / dark_cloud_cover       (2-bar)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import (
    CANDLE_BODY_TOP_MAX,
    CANDLE_HAMMER_BODY_MAX,
    CANDLE_IN_CONTEXT_ATR,
    CANDLE_WICK_MIN,
)


@dataclass
class CandleSignal:
    name: str
    direction: str        # "bullish" | "bearish"
    bar_index: int
    in_context: bool
    distance_to_level_atr: float


def _in_context(bar: Bar, level: float, atr_value: float) -> (bool, float):
    if atr_value <= 0:
        return False, float("inf")
    dist_atr = min(
        abs(bar.high - level),
        abs(bar.low - level),
        abs(bar.close - level),
    ) / atr_value
    return dist_atr <= CANDLE_IN_CONTEXT_ATR, dist_atr


def _is_bullish_engulfing(prev: Bar, cur: Bar) -> bool:
    return (
        prev.close < prev.open  # prev red
        and cur.close > cur.open  # cur green
        and cur.close > prev.open
        and cur.open < prev.close
    )


def _is_bearish_engulfing(prev: Bar, cur: Bar) -> bool:
    return (
        prev.close > prev.open
        and cur.close < cur.open
        and cur.close < prev.open
        and cur.open > prev.close
    )


def _is_hammer(bar: Bar) -> bool:
    rng = bar.high - bar.low
    if rng <= 0:
        return False
    body = abs(bar.close - bar.open)
    lower = min(bar.open, bar.close) - bar.low
    upper = bar.high - max(bar.open, bar.close)
    return (body / rng <= CANDLE_HAMMER_BODY_MAX
            and lower / rng >= CANDLE_WICK_MIN
            and upper / rng <= CANDLE_BODY_TOP_MAX)


def _is_shooting_star(bar: Bar) -> bool:
    rng = bar.high - bar.low
    if rng <= 0:
        return False
    body = abs(bar.close - bar.open)
    lower = min(bar.open, bar.close) - bar.low
    upper = bar.high - max(bar.open, bar.close)
    return (body / rng <= CANDLE_HAMMER_BODY_MAX
            and upper / rng >= CANDLE_WICK_MIN
            and lower / rng <= CANDLE_BODY_TOP_MAX)


def _is_piercing(prev: Bar, cur: Bar) -> bool:
    if not (prev.close < prev.open and cur.close > cur.open):
        return False
    midpoint = (prev.open + prev.close) / 2.0
    return cur.open < prev.close and cur.close >= midpoint and cur.close < prev.open


def _is_dark_cloud(prev: Bar, cur: Bar) -> bool:
    if not (prev.close > prev.open and cur.close < cur.open):
        return False
    midpoint = (prev.open + prev.close) / 2.0
    return cur.open > prev.close and cur.close <= midpoint and cur.close > prev.open


def detect_in_context_candles(bars: Sequence[Bar],
                              *,
                              atr_value: float,
                              levels_prices: Sequence[float],
                              lookback: int = 5) -> List[CandleSignal]:
    """Scan the LAST `lookback` bars for in-context Nison signals.

    Returns only signals where the bar lies within CANDLE_IN_CONTEXT_ATR ×
    ATR of the closest provided level price.
    """
    if not bars or atr_value <= 0 or not levels_prices:
        return []
    out: List[CandleSignal] = []
    start = max(1, len(bars) - lookback)
    for i in range(start, len(bars)):
        cur = bars[i]
        prev = bars[i - 1]
        nearest = min(levels_prices, key=lambda p: abs(cur.close - p))
        ok, dist_atr = _in_context(cur, nearest, atr_value)
        if not ok:
            continue
        if _is_bullish_engulfing(prev, cur):
            out.append(CandleSignal("bullish_engulfing", "bullish", i, True, dist_atr))
        elif _is_bearish_engulfing(prev, cur):
            out.append(CandleSignal("bearish_engulfing", "bearish", i, True, dist_atr))
        elif _is_hammer(cur):
            out.append(CandleSignal("hammer", "bullish", i, True, dist_atr))
        elif _is_shooting_star(cur):
            out.append(CandleSignal("shooting_star", "bearish", i, True, dist_atr))
        elif _is_piercing(prev, cur):
            out.append(CandleSignal("piercing", "bullish", i, True, dist_atr))
        elif _is_dark_cloud(prev, cur):
            out.append(CandleSignal("dark_cloud_cover", "bearish", i, True, dist_atr))
    return out
