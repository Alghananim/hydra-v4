"""HYDRA V11 — additional setup detectors.

V5 had 3 setup types: breakout, retest, pullback. V11 adds:

  - inside_bar_breakout : a small consolidation bar inside the prior
    bar's range, followed by a directional break in the trend
    direction. Common entry on M5.
  - range_break        : different from breakout. Identifies bounded
    range (multiple swings inside [low, high]) and triggers when price
    cleanly breaks the boundary (with body close).
  - mean_reversion_at_sr: counter-trend reversal at a strong S/R level
    when ATR is compressed and a rejection candle forms.

Each detector mirrors V5's pattern: pure-function, returns dataclass,
no global state, no lookahead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from marketmind.v4.models import Bar


# ---------------------------------------------------------------------------
# Inside-bar breakout
# ---------------------------------------------------------------------------


@dataclass
class InsideBarResult:
    is_setup: bool
    direction: str             # "long" | "short" | "none"
    inside_bar_index: int
    breakout_bar_index: int
    reason: str


def detect_inside_bar_breakout(
    bars: Sequence[Bar],
    *,
    atr_value: float,
    trend_label: str,
) -> InsideBarResult:
    """Inside-bar = current bar's high < previous high AND low > previous low.
    Breakout = following bar closes outside the previous bar's range in
    trend direction with body >= 0.5 of range.
    """
    if not bars or len(bars) < 3 or atr_value <= 0:
        return InsideBarResult(False, "none", -1, -1, "no_inputs")
    if trend_label not in ("bullish_strong", "bullish_weak",
                           "bearish_strong", "bearish_weak"):
        return InsideBarResult(False, "none", -1, -1, "no_trend")

    # Look for inside-bar at -2 with breakout at -1.
    parent = bars[-3]
    inside = bars[-2]
    breaker = bars[-1]

    if not (inside.high < parent.high and inside.low > parent.low):
        return InsideBarResult(False, "none", len(bars) - 2, len(bars) - 1,
                                "no_inside_bar")

    rng = breaker.high - breaker.low
    if rng <= 0:
        return InsideBarResult(False, "none", -1, -1, "zero_range_breaker")
    body = abs(breaker.close - breaker.open)
    body_ok = (body / rng) >= 0.5

    if trend_label.startswith("bullish") and breaker.close > parent.high and body_ok:
        return InsideBarResult(
            is_setup=True, direction="long",
            inside_bar_index=len(bars) - 2,
            breakout_bar_index=len(bars) - 1,
            reason="inside_bar_breakout_long",
        )
    if trend_label.startswith("bearish") and breaker.close < parent.low and body_ok:
        return InsideBarResult(
            is_setup=True, direction="short",
            inside_bar_index=len(bars) - 2,
            breakout_bar_index=len(bars) - 1,
            reason="inside_bar_breakout_short",
        )
    return InsideBarResult(False, "none", len(bars) - 2, len(bars) - 1,
                            "inside_found_but_no_breakout")


# ---------------------------------------------------------------------------
# Range break
# ---------------------------------------------------------------------------


@dataclass
class RangeBreakResult:
    is_setup: bool
    direction: str
    range_high: float
    range_low: float
    breakout_bar_index: int
    reason: str


def detect_range_break(
    bars: Sequence[Bar],
    *,
    atr_value: float,
    lookback: int = 30,
) -> RangeBreakResult:
    """Range = last `lookback` bars where high-low is bounded within
    2x ATR AND the bars oscillate (>=2 swings inside).
    Break = current bar closes outside that range with body >= 0.5.
    """
    if not bars or len(bars) < lookback + 1 or atr_value <= 0:
        return RangeBreakResult(False, "none", 0, 0, -1, "no_inputs")

    range_bars = bars[-lookback - 1:-1]   # exclude current bar from range
    rh = max(b.high for b in range_bars)
    rl = min(b.low for b in range_bars)
    range_height = rh - rl
    if range_height > 2.0 * atr_value:
        return RangeBreakResult(False, "none", rh, rl, -1, "range_too_wide")
    if range_height <= 0.5 * atr_value:
        return RangeBreakResult(False, "none", rh, rl, -1, "range_too_narrow")

    # Verify oscillation: at least 2 swings (close direction changes >=4)
    closes = [b.close for b in range_bars]
    flips = sum(1 for i in range(2, len(closes))
                if (closes[i] - closes[i - 1]) * (closes[i - 1] - closes[i - 2]) < 0)
    if flips < 4:
        return RangeBreakResult(False, "none", rh, rl, -1, "not_oscillating")

    breaker = bars[-1]
    body_rng = breaker.high - breaker.low
    if body_rng <= 0:
        return RangeBreakResult(False, "none", rh, rl, -1, "zero_range_breaker")
    body_ok = (abs(breaker.close - breaker.open) / body_rng) >= 0.5

    threshold = 0.3 * atr_value
    if breaker.close > rh + threshold and body_ok:
        return RangeBreakResult(True, "long", rh, rl, len(bars) - 1,
                                  "range_break_up")
    if breaker.close < rl - threshold and body_ok:
        return RangeBreakResult(True, "short", rh, rl, len(bars) - 1,
                                  "range_break_down")
    return RangeBreakResult(False, "none", rh, rl, -1, "no_break")


# ---------------------------------------------------------------------------
# Mean reversion at S/R
# ---------------------------------------------------------------------------


@dataclass
class MeanReversionResult:
    is_setup: bool
    direction: str
    level_price: float
    bar_index: int
    reason: str


def detect_mean_reversion_at_level(
    bars: Sequence[Bar],
    *,
    atr_value: float,
    levels_prices: Sequence[float],
    atr_compressed_pct: float,
) -> MeanReversionResult:
    """Mean reversion fires when:
      - Price is at a strong S/R level (within 0.5 x ATR).
      - ATR is in the compressed band (<= 25 percentile).
      - The most recent bar shows a rejection wick at the level.
      - Direction is opposite the immediate impulse into the level.
    """
    if not bars or atr_value <= 0 or not levels_prices:
        return MeanReversionResult(False, "none", 0, -1, "no_inputs")
    if atr_compressed_pct > 25.0:
        return MeanReversionResult(False, "none", 0, -1,
                                     "vol_not_compressed")

    cur = bars[-1]
    nearest = min(levels_prices, key=lambda p: abs(cur.close - p))
    if abs(cur.close - nearest) > 0.5 * atr_value:
        return MeanReversionResult(False, "none", nearest, -1,
                                     "not_at_level")

    rng = cur.high - cur.low
    if rng <= 0:
        return MeanReversionResult(False, "none", nearest, -1,
                                     "zero_range")

    # Lower wick rejection at support → long
    lower_wick = (min(cur.open, cur.close) - cur.low) / rng
    upper_wick = (cur.high - max(cur.open, cur.close)) / rng
    if lower_wick >= 0.5 and cur.close >= nearest:
        return MeanReversionResult(True, "long", nearest, len(bars) - 1,
                                     "rejection_wick_at_support")
    if upper_wick >= 0.5 and cur.close <= nearest:
        return MeanReversionResult(True, "short", nearest, len(bars) - 1,
                                     "rejection_wick_at_resistance")
    return MeanReversionResult(False, "none", nearest, -1,
                                 "no_rejection_wick")
