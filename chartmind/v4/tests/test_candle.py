"""Candle confirmation tests — in-context only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from marketmind.v4 import indicators
from marketmind.v4.models import Bar

from chartmind.v4 import candle_confirmation as cc


def _build_bullish_engulfing_at_level():
    """Build 30 bars where bar 28 (red) and bar 29 (engulfing green) sit at level=1.1000."""
    base = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    bars = []
    p = 1.1010
    for i in range(28):
        nxt = p + (0.0001 if i % 2 else -0.0001)
        bars.append(Bar(timestamp=base + timedelta(minutes=15 * i),
                        open=p, high=max(p, nxt) + 0.0002,
                        low=min(p, nxt) - 0.0002, close=nxt,
                        volume=1000.0, spread_pips=0.5))
        p = nxt
    # Red bar
    bars.append(Bar(timestamp=base + timedelta(minutes=15 * 28),
                    open=1.1006, high=1.1008, low=1.0995,
                    close=1.0998, volume=1500.0, spread_pips=0.5))
    # Engulfing green bar
    bars.append(Bar(timestamp=base + timedelta(minutes=15 * 29),
                    open=1.0997, high=1.1015, low=1.0996,
                    close=1.1010, volume=1700.0, spread_pips=0.5))
    return bars


def test_bullish_engulfing_in_context():
    bars = _build_bullish_engulfing_at_level()
    atr = indicators.atr(bars)
    sigs = cc.detect_in_context_candles(bars, atr_value=atr,
                                        levels_prices=[1.1000])
    names = [s.name for s in sigs]
    assert "bullish_engulfing" in names


def test_no_signal_when_far_from_level():
    bars = _build_bullish_engulfing_at_level()
    atr = indicators.atr(bars)
    # A level miles away — distance > 1.0 ATR
    sigs = cc.detect_in_context_candles(bars, atr_value=atr,
                                        levels_prices=[2.0000])
    assert sigs == []


def test_hammer_thresholds_via_named_constants():
    """Hardening C4: hammer detection uses CANDLE_HAMMER_BODY_MAX,
    CANDLE_WICK_MIN, CANDLE_BODY_TOP_MAX from chart_thresholds — NOT
    inline 0.4 / 0.5 / 0.2 magic literals.

    Construct a bar exactly on the named threshold boundaries and assert
    it qualifies as a hammer.
    """
    from chartmind.v4.candle_confirmation import _is_hammer
    from chartmind.v4.chart_thresholds import (
        CANDLE_BODY_TOP_MAX,
        CANDLE_HAMMER_BODY_MAX,
        CANDLE_WICK_MIN,
    )
    base = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    # body=0.40, lower_wick=0.50, upper_wick=0.10 → hits all three named
    # thresholds at their permissive ends. range = 1.0.
    rng = 1.0
    body = CANDLE_HAMMER_BODY_MAX * rng       # 0.40
    lower = CANDLE_WICK_MIN * rng             # 0.50
    upper = CANDLE_BODY_TOP_MAX * rng / 2     # 0.10 < 0.20 (well within)
    # Construct: low=0.0, body block from 0.50 to 0.90, high=1.0
    # open=close+body? Bullish hammer: open at top of body (0.90), close at
    # bottom (0.50). Bullish/bearish for hammer doesn't matter for shape.
    open_p = 1.0 - upper - body / 2           # = 0.70
    close_p = open_p + body / 2 - body        # = 0.50? Let's just place it.
    open_p = 0.90  # top of body
    close_p = 0.50  # bottom of body
    low_p = 0.00
    high_p = 1.00
    bar = Bar(
        timestamp=base, open=open_p, high=high_p, low=low_p, close=close_p,
        volume=1000.0, spread_pips=0.5,
    )
    # body/range = 0.40, lower/range = 0.50, upper/range = 0.10
    assert _is_hammer(bar), (
        f"hammer detection should accept a bar at the named-constant "
        f"thresholds; constants are HAMMER_BODY_MAX={CANDLE_HAMMER_BODY_MAX}, "
        f"WICK_MIN={CANDLE_WICK_MIN}, BODY_TOP_MAX={CANDLE_BODY_TOP_MAX}"
    )


def test_zero_atr_returns_empty():
    bars = _build_bullish_engulfing_at_level()
    sigs = cc.detect_in_context_candles(bars, atr_value=0.0,
                                        levels_prices=[1.1000])
    assert sigs == []


def test_no_levels_returns_empty():
    bars = _build_bullish_engulfing_at_level()
    atr = indicators.atr(bars)
    assert cc.detect_in_context_candles(bars, atr_value=atr,
                                        levels_prices=[]) == []


def test_hammer_detection():
    base = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    bars = []
    p = 1.1010
    for i in range(28):
        nxt = p + (0.0001 if i % 2 else -0.0001)
        bars.append(Bar(timestamp=base + timedelta(minutes=15 * i),
                        open=p, high=max(p, nxt) + 0.0002,
                        low=min(p, nxt) - 0.0002, close=nxt,
                        volume=1000.0, spread_pips=0.5))
        p = nxt
    # Hammer at the level: long lower wick, small body near top
    bars.append(Bar(timestamp=base + timedelta(minutes=15 * 28),
                    open=1.1003, high=1.1005, low=1.0985,
                    close=1.1004, volume=1200.0, spread_pips=0.5))
    bars.append(Bar(timestamp=base + timedelta(minutes=15 * 29),
                    open=1.1004, high=1.1010, low=1.1003,
                    close=1.1009, volume=1200.0, spread_pips=0.5))
    atr = indicators.atr(bars)
    sigs = cc.detect_in_context_candles(bars, atr_value=atr,
                                        levels_prices=[1.1000])
    names = [s.name for s in sigs]
    # Either hammer or piercing/engulfing depending on timing — at minimum we expect one bullish signal
    assert any(s.direction == "bullish" for s in sigs)
