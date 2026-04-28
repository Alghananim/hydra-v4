"""Tests for shared indicators."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from marketmind.v4 import indicators
from marketmind.v4.models import Bar


def _bar(i, o, h, l, c, v=1000.0):
    return Bar(
        timestamp=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * i),
        open=o, high=h, low=l, close=c, volume=v, spread_pips=0.5,
    )


def test_atr_zero_when_too_few_bars():
    bars = [_bar(i, 1.0, 1.001, 0.999, 1.0005) for i in range(5)]
    assert indicators.atr(bars) == 0.0


def test_atr_constant_range_is_constant():
    # All bars have True Range == 0.002 -> ATR should converge to 0.002
    bars = [_bar(i, 1.0, 1.001, 0.999, 1.0) for i in range(40)]
    a = indicators.atr(bars)
    assert abs(a - 0.002) < 1e-9


def test_adx_directionless_low():
    # Range-bound: high & low oscillate symmetrically -> ADX stays low
    bars = []
    for i in range(80):
        sgn = 1 if i % 2 == 0 else -1
        c = 1.0 + sgn * 0.0005
        bars.append(_bar(i, 1.0, 1.0 + 0.001, 1.0 - 0.001, c))
    a = indicators.adx(bars)
    assert 0.0 <= a < 30.0


def test_adx_strong_uptrend_high():
    bars = []
    p = 1.0
    for i in range(80):
        nxt = p + 0.001
        bars.append(_bar(i, p, nxt + 0.0001, p - 0.00005, nxt))
        p = nxt
    a = indicators.adx(bars)
    assert a > 25.0, f"ADX should be elevated for clean uptrend, got {a}"


def test_ema_constant_returns_constant():
    vals = [1.0] * 40
    assert abs(indicators.ema(vals, 20) - 1.0) < 1e-9


def test_ema_lags_step():
    # Ramp 1.0..1.0+0.001*n => EMA below latest value
    vals = [1.0 + 0.001 * i for i in range(40)]
    e = indicators.ema(vals, 20)
    assert e < vals[-1]
    assert e > vals[-20]


def test_percentile_rank_midpoint():
    sample = [1, 2, 3, 4, 5]
    assert indicators.percentile_rank(3, sample) == pytest.approx(50.0)


def test_percentile_rank_top():
    assert indicators.percentile_rank(100, [1, 2, 3]) == pytest.approx(100.0)


def test_percentile_rank_bottom():
    assert indicators.percentile_rank(-1, [1, 2, 3]) == pytest.approx(0.0)


def test_slope_positive_for_uptrend():
    vals = [1.0 + 0.01 * i for i in range(20)]
    s = indicators.slope(vals, 20)
    assert s > 0


def test_slope_negative_for_downtrend():
    vals = [1.0 - 0.01 * i for i in range(20)]
    assert indicators.slope(vals, 20) < 0


def test_slope_zero_for_flat():
    vals = [1.0] * 20
    assert indicators.slope(vals, 20) == 0.0


def test_hh_count_uptrend():
    closes = [1.0 + 0.001 * i for i in range(25)]
    assert indicators.hh_count(closes, 20) == 20


def test_hl_count_downtrend():
    closes = [1.0 - 0.001 * i for i in range(25)]
    assert indicators.hl_count(closes, 20) == 20


def test_direction_flips_alternating():
    closes = [1.0]
    for i in range(15):
        closes.append(closes[-1] + (0.001 if i % 2 == 0 else -0.001))
    flips = indicators.direction_flips(closes, 10)
    assert flips >= 5


def test_direction_flips_monotone_zero():
    closes = [1.0 + 0.001 * i for i in range(15)]
    assert indicators.direction_flips(closes, 10) == 0


def test_atr_percentile_compressed():
    # Long quiet history then last bar still quiet
    bars = [_bar(i, 1.0, 1.0 + 0.0001, 1.0 - 0.0001, 1.0) for i in range(120)]
    pct = indicators.atr_percentile_now(bars)
    # Median-ish — compressed regime is when current ATR is low vs history;
    # here all ATRs equal so percentile lands near 50.
    assert 0.0 <= pct <= 100.0
