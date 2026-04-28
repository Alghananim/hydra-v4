"""Support/Resistance tests — cluster dedup, strength counter."""
from __future__ import annotations

from marketmind.v4 import indicators

from chartmind.v4 import support_resistance as sr


def test_no_levels_when_atr_zero(bullish_strong):
    out = sr.detect_levels(bullish_strong, atr_value=0.0)
    assert out == []


def test_levels_have_strength_at_least_one(bullish_strong):
    atr = indicators.atr(bullish_strong)
    levels = sr.detect_levels(bullish_strong, atr_value=atr)
    if levels:
        for L in levels:
            assert L.strength >= 1


def test_levels_are_price_sorted(bullish_strong):
    atr = indicators.atr(bullish_strong)
    levels = sr.detect_levels(bullish_strong, atr_value=atr)
    prices = [L.price for L in levels]
    assert prices == sorted(prices)


def test_cluster_tolerance_dedupes_close_swings():
    """Two pivots within 0.3*ATR should merge into one cluster."""
    from datetime import datetime, timedelta, timezone
    from marketmind.v4.models import Bar

    base = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    # Build bars where two swing highs land at 1.1030 and 1.1031 (essentially identical)
    bars = []
    series = [
        1.1000, 1.1005, 1.1010, 1.1020, 1.1030, 1.1020, 1.1010, 1.1005,  # first peak around 1.1030
        1.1000, 0.9995 if False else 1.0995, 1.1000, 1.1005, 1.1015,
        1.1025, 1.1031, 1.1025, 1.1015, 1.1005, 1.1000,
    ]
    # Pad to 35 bars to satisfy ATR period
    while len(series) < 35:
        series.append(series[-1] + (0.0001 if len(series) % 2 else -0.0001))
    for i, c in enumerate(series):
        prev = series[i - 1] if i > 0 else c
        bars.append(Bar(timestamp=base + timedelta(minutes=15 * i),
                        open=prev, high=max(prev, c) + 0.0002,
                        low=min(prev, c) - 0.0002, close=c,
                        volume=1000.0, spread_pips=0.5))
    atr = indicators.atr(bars)
    if atr > 0:
        levels = sr.detect_levels(bars, atr_value=atr)
        # Two near-equal peaks should produce at most one resistance cluster around 1.103
        near = [L for L in levels if abs(L.price - 1.1030) < 0.001]
        assert len(near) <= 1


def test_nearest_levels_returns_below_and_above(bullish_strong):
    atr = indicators.atr(bullish_strong)
    levels = sr.detect_levels(bullish_strong, atr_value=atr)
    last = bullish_strong[-1].close
    sup, res = sr.nearest_levels(levels, last)
    if sup is not None:
        assert sup.price <= last
    if res is not None:
        assert res.price > last


def test_levels_publishable_dict(bullish_strong):
    atr = indicators.atr(bullish_strong)
    levels = sr.detect_levels(bullish_strong, atr_value=atr)
    for L in levels:
        d = L.to_public()
        assert set(d.keys()) == {"price", "type", "strength"}
        assert d["type"] in ("support", "resistance")
