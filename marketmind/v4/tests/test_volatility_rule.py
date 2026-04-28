"""VOL_RULE: 4 states."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from marketmind.v4 import volatility_rule
from marketmind.v4.models import Bar
from marketmind.v4.tests.conftest import (
    make_ranging_bars,
    make_volatility_spike,
)


def _quiet_then_loud(n_quiet=110, n_loud=10):
    """Mostly tiny ranges, then several wide bars at the end -> expanded/dangerous."""
    base = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    bars: List[Bar] = []
    p = 1.0
    for i in range(n_quiet):
        nxt = p * (1 + 0.00005)
        bars.append(Bar(
            timestamp=base + timedelta(minutes=15 * i),
            open=p, high=p * 1.00005, low=p * 0.99995, close=nxt,
            volume=1000.0, spread_pips=0.5,
        ))
        p = nxt
    for j in range(n_loud):
        nxt = p * (1 + 0.001)
        bars.append(Bar(
            timestamp=base + timedelta(minutes=15 * (n_quiet + j)),
            open=p, high=p * 1.003, low=p * 0.997, close=nxt,
            volume=2000.0, spread_pips=0.5,
        ))
        p = nxt
    return bars


def test_unknown_too_few():
    bars = make_ranging_bars(n=10)
    s, ev = volatility_rule.evaluate(bars)
    assert s == "unknown", ev


def test_normal_range_stays_normal():
    bars = make_ranging_bars(n=120)
    s, ev = volatility_rule.evaluate(bars)
    # Equal-ATR series will cluster percentiles around 50 -> normal
    assert s == "normal", ev


def test_dangerous_on_extreme_last_bar():
    bars = make_volatility_spike(n=120)
    s, ev = volatility_rule.evaluate(bars)
    assert s == "dangerous", ev


def test_expanded_when_recent_atr_high_vs_history():
    bars = _quiet_then_loud(110, 10)
    s, ev = volatility_rule.evaluate(bars)
    # Recent ATR has been climbing — expect expanded or dangerous
    assert s in ("expanded", "dangerous"), ev


def test_compressed_when_recent_atr_low_vs_history():
    # Loud history then quiet last 20 bars
    base = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    bars: List[Bar] = []
    p = 1.0
    for i in range(110):
        nxt = p * (1 + 0.0008)
        bars.append(Bar(
            timestamp=base + timedelta(minutes=15 * i),
            open=p, high=p * 1.003, low=p * 0.997, close=nxt,
            volume=1500.0, spread_pips=0.5,
        ))
        p = nxt
    for j in range(20):
        nxt = p * (1 + 0.00005)
        bars.append(Bar(
            timestamp=base + timedelta(minutes=15 * (110 + j)),
            open=p, high=p * 1.00005, low=p * 0.99995, close=nxt,
            volume=900.0, spread_pips=0.5,
        ))
        p = nxt
    s, ev = volatility_rule.evaluate(bars)
    assert s in ("compressed", "normal"), ev
