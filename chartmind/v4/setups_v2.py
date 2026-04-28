"""ChartMind V4 — V2 setup expansion (HYDRA V2 brain redesign).

V5 ChartMind detected 3 setups: breakout, retest, pullback. Measured
directional rate on EUR/USD + USD/JPY M15 = 0.15 % of in-window cycles
(53 ENTERs over 99,298 cycles in 2 years).

V2-W1 adds 5 new pattern detectors that fire on cycles V5 silently
ignored. All five are pure functions, no global state, no lookahead,
returning a boolean evidence flag plus a direction.

The five setups:
    1. inside_bar_breakout       — small consolidation followed by
                                   trend-direction break (M15-tuned)
    2. range_break               — bounded range (multiple swings inside
                                   2x ATR) cleanly broken with body
    3. mean_reversion_at_level   — counter-trend reversal at strong S/R
                                   when ATR compressed and rejection wick
    4. momentum_thrust           — single wide-range body bar in trend
                                   direction with close in upper/lower
                                   third (no level required)
    5. opening_range_break       — break of the first hour's range
                                   during NY session (institutional
                                   convention)

Each function returns a SetupResult dataclass with:
    - is_setup: bool
    - direction: "long" | "short" | "none"
    - reason: str

The V2 ChartMind orchestrator will (a) prefer V5's primary
breakout/retest/pullback detection (preserves V5 invariants) AND
(b) additively wire each V2 detector as an evidence flag. This means
the new detectors EXPAND coverage without weakening the existing
quality bar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from marketmind.v4.models import Bar


@dataclass
class SetupResult:
    is_setup: bool
    direction: str          # "long" | "short" | "none"
    reason: str
    bar_index: int = -1


# ---------------------------------------------------------------------------
# 1. Inside-bar breakout (M15-tuned port of V11)
# ---------------------------------------------------------------------------


def detect_inside_bar(bars: Sequence[Bar], *,
                      atr_value: float,
                      trend_label: str) -> SetupResult:
    """Inside-bar = bar at -2 fully inside parent at -3.
    Breakout = bar at -1 closes outside parent range with body >= 0.5
    of its own range, in trend direction."""
    if not bars or len(bars) < 3 or atr_value <= 0:
        return SetupResult(False, "none", "no_inputs")
    if trend_label not in ("bullish_strong", "bullish_weak",
                           "bearish_strong", "bearish_weak"):
        return SetupResult(False, "none", "no_trend")

    parent = bars[-3]
    inside = bars[-2]
    breaker = bars[-1]

    if not (inside.high < parent.high and inside.low > parent.low):
        return SetupResult(False, "none", "no_inside_bar")

    rng = breaker.high - breaker.low
    if rng <= 0:
        return SetupResult(False, "none", "zero_range_breaker")
    body_ok = (abs(breaker.close - breaker.open) / rng) >= 0.5

    if trend_label.startswith("bullish") and breaker.close > parent.high and body_ok:
        return SetupResult(True, "long", "inside_bar_break_long",
                           bar_index=len(bars) - 1)
    if trend_label.startswith("bearish") and breaker.close < parent.low and body_ok:
        return SetupResult(True, "short", "inside_bar_break_short",
                           bar_index=len(bars) - 1)
    return SetupResult(False, "none", "inside_no_break")


# ---------------------------------------------------------------------------
# 2. Range break
# ---------------------------------------------------------------------------


def detect_range_break(bars: Sequence[Bar], *,
                        atr_value: float,
                        lookback: int = 30) -> SetupResult:
    """Range = last `lookback` closed bars where max(high) - min(low)
    is between 0.5x and 2.0x ATR with at least 4 close-direction flips
    (oscillating). Break = current bar closes outside range by 0.3x ATR
    with body >= 0.5 of its own range.
    """
    if not bars or len(bars) < lookback + 1 or atr_value <= 0:
        return SetupResult(False, "none", "no_inputs")

    range_bars = bars[-lookback - 1:-1]
    rh = max(b.high for b in range_bars)
    rl = min(b.low for b in range_bars)
    height = rh - rl
    if height > 2.0 * atr_value:
        return SetupResult(False, "none", "range_too_wide")
    if height <= 0.5 * atr_value:
        return SetupResult(False, "none", "range_too_narrow")

    closes = [b.close for b in range_bars]
    flips = sum(1 for i in range(2, len(closes))
                if (closes[i] - closes[i - 1]) * (closes[i - 1] - closes[i - 2]) < 0)
    if flips < 4:
        return SetupResult(False, "none", "not_oscillating")

    breaker = bars[-1]
    body_rng = breaker.high - breaker.low
    if body_rng <= 0:
        return SetupResult(False, "none", "zero_range_breaker")
    body_ok = (abs(breaker.close - breaker.open) / body_rng) >= 0.5

    threshold = 0.3 * atr_value
    if breaker.close > rh + threshold and body_ok:
        return SetupResult(True, "long", "range_break_up",
                           bar_index=len(bars) - 1)
    if breaker.close < rl - threshold and body_ok:
        return SetupResult(True, "short", "range_break_down",
                           bar_index=len(bars) - 1)
    return SetupResult(False, "none", "no_break")


# ---------------------------------------------------------------------------
# 3. Mean reversion at S/R level
# ---------------------------------------------------------------------------


def detect_mean_reversion(bars: Sequence[Bar], *,
                          atr_value: float,
                          levels_prices: Sequence[float],
                          atr_percentile_now: float) -> SetupResult:
    """Counter-trend rejection at strong S/R.
    Fires when ATR is compressed (<= 25th percentile), price is within
    0.5x ATR of a level, and the most recent bar shows a rejection
    wick >= 0.5 of its range that closes back on the same side.
    """
    if not bars or atr_value <= 0 or not levels_prices:
        return SetupResult(False, "none", "no_inputs")
    if atr_percentile_now > 25.0:
        return SetupResult(False, "none", "vol_not_compressed")

    cur = bars[-1]
    nearest = min(levels_prices, key=lambda p: abs(cur.close - p))
    if abs(cur.close - nearest) > 0.5 * atr_value:
        return SetupResult(False, "none", "not_at_level")

    rng = cur.high - cur.low
    if rng <= 0:
        return SetupResult(False, "none", "zero_range")

    lower_wick = (min(cur.open, cur.close) - cur.low) / rng
    upper_wick = (cur.high - max(cur.open, cur.close)) / rng
    if lower_wick >= 0.5 and cur.close >= nearest:
        return SetupResult(True, "long", "mr_long_at_support",
                           bar_index=len(bars) - 1)
    if upper_wick >= 0.5 and cur.close <= nearest:
        return SetupResult(True, "short", "mr_short_at_resistance",
                           bar_index=len(bars) - 1)
    return SetupResult(False, "none", "no_rejection_wick")


# ---------------------------------------------------------------------------
# 4. Momentum thrust (NEW)
# ---------------------------------------------------------------------------


def detect_momentum_thrust(bars: Sequence[Bar], *,
                           atr_value: float,
                           trend_label: str) -> SetupResult:
    """Single wide-range bar in trend direction.
    Conditions:
      - Bar range >= 1.4x ATR (wide)
      - Body / range >= 0.6 (decisive close, not exhaustion)
      - Close in upper third for long (or lower third for short)
      - Trend label is directional (bullish_* or bearish_*)
      - Two prior closes confirm continuation: close[-2] and close[-3]
        progress in trend direction (close_now > close_-2 > close_-3 for long).
    No level confluence required — this is the "trend continues" pattern
    that V5 currently misses entirely (it only sees breakouts at levels).
    """
    if not bars or len(bars) < 4 or atr_value <= 0:
        return SetupResult(False, "none", "no_inputs")
    if trend_label not in ("bullish_strong", "bullish_weak",
                           "bearish_strong", "bearish_weak"):
        return SetupResult(False, "none", "no_trend")

    cur = bars[-1]
    rng = cur.high - cur.low
    if rng <= 0:
        return SetupResult(False, "none", "zero_range")
    if rng < 1.4 * atr_value:
        return SetupResult(False, "none", "range_too_small")
    body = abs(cur.close - cur.open)
    if body / rng < 0.6:
        return SetupResult(False, "none", "body_too_small")

    close_loc = (cur.close - cur.low) / rng

    c_2 = bars[-2].close
    c_3 = bars[-3].close

    if trend_label.startswith("bullish"):
        if close_loc < 0.66:
            return SetupResult(False, "none", "close_not_upper_third")
        if not (cur.close > c_2 > c_3):
            return SetupResult(False, "none", "no_progression_long")
        return SetupResult(True, "long", "momentum_thrust_long",
                           bar_index=len(bars) - 1)
    else:  # bearish
        if close_loc > 0.34:
            return SetupResult(False, "none", "close_not_lower_third")
        if not (cur.close < c_2 < c_3):
            return SetupResult(False, "none", "no_progression_short")
        return SetupResult(True, "short", "momentum_thrust_short",
                           bar_index=len(bars) - 1)


# ---------------------------------------------------------------------------
# 5. Opening-range break (NEW)
# ---------------------------------------------------------------------------


def detect_opening_range_break(bars: Sequence[Bar], *,
                               atr_value: float,
                               now_utc_hour: int,
                               session_start_utc_hour: int = 13) -> SetupResult:
    """Opening-range = first hour (4 M15 bars) of the NY session.
    Default session start = 13:00 UTC (08:00 ET, post-DST).
    Setup = current bar (after the OR is established) closes outside the
    OR by 0.3x ATR with body >= 0.5 of its own range.

    Only fires when:
      - now_utc_hour is in {session_start..session_start+5} (first 5 hours)
      - We have at least 4 bars after the open of OR construction.
    """
    if not bars or len(bars) < 5 or atr_value <= 0:
        return SetupResult(False, "none", "no_inputs")
    # Session window: first 5 hours of NY session.
    if not (session_start_utc_hour <= now_utc_hour < session_start_utc_hour + 5):
        return SetupResult(False, "none", "outside_orb_window")

    # Find the FIRST 4 bars whose timestamps fall within the session_start hour.
    # We assume bars are M15 and timestamped at OPEN time.
    or_bars = []
    for b in bars[-30:]:  # search the most recent ~7.5h of M15
        ts = b.timestamp
        if ts.hour == session_start_utc_hour:
            or_bars.append(b)
        elif or_bars:
            # We've moved past the session-start hour.
            break

    if len(or_bars) < 4:
        return SetupResult(False, "none", "or_bars_incomplete")

    or_high = max(b.high for b in or_bars[:4])
    or_low = min(b.low for b in or_bars[:4])
    if or_high - or_low <= 0:
        return SetupResult(False, "none", "or_range_zero")

    breaker = bars[-1]
    # Don't fire on the OR bars themselves.
    if breaker in or_bars[:4]:
        return SetupResult(False, "none", "still_in_or")

    rng = breaker.high - breaker.low
    if rng <= 0:
        return SetupResult(False, "none", "zero_range_breaker")
    body_ok = (abs(breaker.close - breaker.open) / rng) >= 0.5
    threshold = 0.3 * atr_value

    if breaker.close > or_high + threshold and body_ok:
        return SetupResult(True, "long", "orb_long",
                           bar_index=len(bars) - 1)
    if breaker.close < or_low - threshold and body_ok:
        return SetupResult(True, "short", "orb_short",
                           bar_index=len(bars) - 1)
    return SetupResult(False, "none", "no_break")
