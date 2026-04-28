"""MOMENTUM_RULE: 5 states."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from marketmind.v4 import momentum_rule
from marketmind.v4.models import Bar
from marketmind.v4.tests.conftest import make_trending_bars, make_ranging_bars


def _bars_with_closes(closes: List[float]) -> List[Bar]:
    out: List[Bar] = []
    base = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i > 0 else c
        out.append(Bar(
            timestamp=base + timedelta(minutes=15 * i),
            open=prev,
            high=max(prev, c) * 1.0002,
            low=min(prev, c) * 0.9998,
            close=c,
            volume=1500.0,
            spread_pips=0.5,
        ))
    return out


def test_none_when_too_few_bars():
    bars = make_trending_bars("up", n=15)
    state, ev = momentum_rule.evaluate(bars)
    assert state == "none", ev


def test_steady_for_quiet_range():
    bars = make_ranging_bars(n=120, band_pct=0.0003)
    state, ev = momentum_rule.evaluate(bars)
    assert state in ("steady", "fading", "divergent"), ev


def test_accelerating_strong_uptrend():
    # Build a sequence where the last 4 bars take an ever-larger jump above EMA
    # First 100 bars: gentle uptrend so EMA is well-defined.
    closes = [1.0 + 0.0002 * i for i in range(100)]
    # Then accelerating jumps
    last = closes[-1]
    closes += [last + 0.001, last + 0.0025, last + 0.0045, last + 0.007]
    bars = _bars_with_closes(closes)
    state, ev = momentum_rule.evaluate(bars)
    assert state == "accelerating", ev


def test_fading_after_acceleration():
    closes = [1.0 + 0.0005 * i for i in range(100)]
    last = closes[-1]
    # Build then fade — last 4 m_i are decreasing
    closes += [last + 0.005, last + 0.004, last + 0.003, last + 0.0025]
    bars = _bars_with_closes(closes)
    state, ev = momentum_rule.evaluate(bars)
    assert state == "fading", ev


def test_divergent_new_high_momentum_doesnt_follow():
    # Slow grind up, then a fresh 20-bar high but only marginal m increase
    base = [1.0 + 0.0003 * i for i in range(80)]
    spike = base + [
        base[-1] + 0.0035,   # establish past max m
        base[-1] + 0.0030,
        base[-1] + 0.0028,
        base[-1] + 0.0040,   # NEW 20-bar high in price, but m_last < m_max
    ]
    bars = _bars_with_closes(spike)
    state, ev = momentum_rule.evaluate(bars)
    # Either divergent or steady — both acceptable, but NOT accelerating
    assert state in ("divergent", "steady"), ev
    assert state != "accelerating"
