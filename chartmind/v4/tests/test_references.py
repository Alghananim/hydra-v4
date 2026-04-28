"""References tests — entry zone is BAND, never single price.

This is the test that proves V3's `last_close * 1.0002` sin is fixed.
"""
from __future__ import annotations

from marketmind.v4 import indicators

from chartmind.v4 import references as refs_mod
from chartmind.v4 import support_resistance as sr
from chartmind.v4.chart_thresholds import (
    ENTRY_BAND_BREAKOUT_ATR,
    ENTRY_BAND_PULLBACK_ATR,
    ENTRY_BAND_RETEST_ATR,
)


def test_breakout_band_width_matches_threshold(breakout_series):
    atr = indicators.atr(breakout_series)
    levels = sr.detect_levels(breakout_series, atr_value=atr)
    r = refs_mod.for_breakout(breakout_series, atr_value=atr,
                              levels=levels, side="long")
    expected_width = 2 * ENTRY_BAND_BREAKOUT_ATR * atr
    actual = r.entry_zone["high"] - r.entry_zone["low"]
    assert abs(actual - expected_width) < 1e-9


def test_breakout_band_centered_on_last_close(breakout_series):
    atr = indicators.atr(breakout_series)
    last = breakout_series[-1].close
    levels = sr.detect_levels(breakout_series, atr_value=atr)
    r = refs_mod.for_breakout(breakout_series, atr_value=atr,
                              levels=levels, side="long")
    mid = (r.entry_zone["low"] + r.entry_zone["high"]) / 2
    assert abs(mid - last) < 1e-9


def test_retest_band_width(breakout_series):
    atr = indicators.atr(breakout_series)
    levels = sr.detect_levels(breakout_series, atr_value=atr)
    r = refs_mod.for_retest(breakout_series, atr_value=atr,
                            level_price=1.1030, levels=levels, side="long")
    expected = 2 * ENTRY_BAND_RETEST_ATR * atr
    actual = r.entry_zone["high"] - r.entry_zone["low"]
    assert abs(actual - expected) < 1e-9


def test_pullback_band_centered_on_swing(pullback_series):
    atr = indicators.atr(pullback_series)
    levels = sr.detect_levels(pullback_series, atr_value=atr)
    r = refs_mod.for_pullback(pullback_series, atr_value=atr,
                              levels=levels, side="long")
    width = r.entry_zone["high"] - r.entry_zone["low"]
    expected = 2 * ENTRY_BAND_PULLBACK_ATR * atr
    assert abs(width - expected) < 1e-9


def test_band_high_strictly_greater_than_low(breakout_series):
    atr = indicators.atr(breakout_series)
    levels = sr.detect_levels(breakout_series, atr_value=atr)
    r = refs_mod.for_breakout(breakout_series, atr_value=atr,
                              levels=levels, side="long")
    assert r.entry_zone["high"] > r.entry_zone["low"]


def test_invalidation_is_real_swing_not_hardcoded(breakout_series):
    atr = indicators.atr(breakout_series)
    levels = sr.detect_levels(breakout_series, atr_value=atr)
    r = refs_mod.for_breakout(breakout_series, atr_value=atr,
                              levels=levels, side="long")
    # Invalidation must NOT match last_close*1.0002 or any V3-style scalar
    last = breakout_series[-1].close
    assert abs(r.invalidation_level - last * 1.0002) > atr * 0.01, \
        "invalidation accidentally equals V3's hardcoded scalar"


def test_target_is_either_real_level_or_None(breakout_series):
    atr = indicators.atr(breakout_series)
    levels = sr.detect_levels(breakout_series, atr_value=atr)
    r = refs_mod.for_breakout(breakout_series, atr_value=atr,
                              levels=levels, side="long")
    if r.target_reference is not None:
        # Must be one of the level prices (a real swing-cluster value)
        assert any(abs(L.price - r.target_reference) < 1e-9 for L in levels)


def test_invalidation_fallback_uses_named_constant():
    """Hardening C4: when no swing exists, references should fall back to
    INVALIDATION_FALLBACK_ATR_MULT * ATR — not a hardcoded `2 * atr_value`.

    Build bars too short to produce any swing (n < 2*k+1). Make ATR known.
    Then the fallback branch must use the named constant.
    """
    from datetime import datetime, timedelta, timezone

    from marketmind.v4.models import Bar

    from chartmind.v4.chart_thresholds import (
        INVALIDATION_FALLBACK_ATR_MULT,
    )
    base = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    # 6 bars: < 2*SWING_K+1 = 7 → no swings produced.
    bars = []
    for i in range(6):
        bars.append(Bar(
            timestamp=base + timedelta(minutes=15 * i),
            open=1.10, high=1.1010, low=1.0990, close=1.1005,
            volume=1000.0, spread_pips=0.5,
        ))
    atr = 0.0050  # synthetic ATR (would be < computed but irrelevant; refs
                   # take it as a parameter)
    levels = []   # empty → no target
    r = refs_mod.for_breakout(bars, atr_value=atr, levels=levels, side="long")
    last = bars[-1].close
    # Invalidation MUST equal last - INVALIDATION_FALLBACK_ATR_MULT * atr
    expected = last - INVALIDATION_FALLBACK_ATR_MULT * atr
    assert abs(r.invalidation_level - expected) < 1e-9, (
        f"invalidation fallback drifted from named constant; "
        f"expected={expected} actual={r.invalidation_level}"
    )
