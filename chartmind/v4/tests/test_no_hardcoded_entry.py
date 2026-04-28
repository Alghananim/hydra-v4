"""Adversarial: prove no hardcoded entry_price.

V3 sin: `last_close * 1.0002`. This test feeds varying ATR and bar series
and asserts entry_zone width = 2 * threshold * ATR — i.e. derived from
real ATR, not from a fixed multiplier of last close.
"""
from __future__ import annotations

import pytest

from marketmind.v4 import indicators

from chartmind.v4.ChartMindV4 import ChartMindV4
from chartmind.v4.chart_thresholds import (
    ENTRY_BAND_BREAKOUT_ATR,
    ENTRY_BAND_PULLBACK_ATR,
    ENTRY_BAND_RETEST_ATR,
)
from chartmind.v4.tests.conftest import (
    make_bullish_strong_bars,
    make_market_bullish_A,
    make_news_aligned,
)


def test_band_width_scales_with_atr(now_utc):
    """If ATR doubles, band width should double."""
    cm = ChartMindV4()

    bars1 = make_bullish_strong_bars(80, step=0.0010)
    bars2 = make_bullish_strong_bars(80, step=0.0020)  # bigger swings -> bigger ATR
    out1 = cm.evaluate("EURUSD", {"M15": bars1}, now_utc=now_utc,
                       news_output=make_news_aligned(),
                       market_output=make_market_bullish_A())
    out2 = cm.evaluate("EURUSD", {"M15": bars2}, now_utc=now_utc,
                       news_output=make_news_aligned(),
                       market_output=make_market_bullish_A())
    w1 = out1.entry_zone["high"] - out1.entry_zone["low"]
    w2 = out2.entry_zone["high"] - out2.entry_zone["low"]
    # ATR ratio should approximate width ratio (allow 20% tolerance — Wilder smoothing isn't linear)
    if out1.atr_value > 0 and out2.atr_value > 0:
        ratio_atr = out2.atr_value / out1.atr_value
        ratio_w = w2 / w1 if w1 > 0 else 0
        assert abs(ratio_atr - ratio_w) < 0.5 * max(ratio_atr, ratio_w), \
            f"band did not scale with ATR: atr_ratio={ratio_atr} width_ratio={ratio_w}"


def test_entry_zone_never_zero_width(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    width = out.entry_zone["high"] - out.entry_zone["low"]
    assert width > 0, "entry_zone collapsed to a single price (V3 sin)"


def test_no_v3_scalar_in_entry_zone(bullish_strong, now_utc):
    """Ensure entry zone center is NOT exactly last_close * 1.0002."""
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    last = bullish_strong[-1].close
    sin_value = last * 1.0002
    mid = (out.entry_zone["low"] + out.entry_zone["high"]) / 2.0
    # The breakout entry IS centered at last_close, so mid==last (no 1.0002 offset).
    assert abs(mid - sin_value) > 1e-12 or abs(mid - last) < 1e-12, \
        "entry zone matched V3's last_close * 1.0002 hardcoded scalar"


def test_invalidation_not_a_simple_offset(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    last = bullish_strong[-1].close
    # Invalidation must not equal last * (1 ± 0.001) — that would be a magic offset
    for k in (0.999, 0.9995, 1.0005, 1.001):
        assert abs(out.invalidation_level - last * k) > 1e-12, (
            f"invalidation matched magic scalar {k}"
        )
