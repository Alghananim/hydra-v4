"""LIQ_RULE: 4 states."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from marketmind.v4 import liquidity_rule
from marketmind.v4.models import Bar


def _bars_at_hour(n=50, hour=13, spread=0.5, vol=2000.0):
    """All bars at the same hour-of-day (UTC)."""
    base = datetime(2026, 4, 27, hour, 0, tzinfo=timezone.utc)
    out = []
    p = 1.1
    for i in range(n):
        ts = base + timedelta(days=i)
        nxt = p * (1 + 0.0001)
        out.append(Bar(timestamp=ts, open=p, high=nxt * 1.0001, low=p * 0.9999,
                       close=nxt, volume=vol, spread_pips=spread))
        p = nxt
    return out


def test_unknown_too_few():
    bars = _bars_at_hour(3)
    s, ev = liquidity_rule.evaluate(bars)
    assert s == "unknown", ev


def test_off_session_overrides():
    bars = _bars_at_hour(50, hour=23)   # off-session
    s, ev = liquidity_rule.evaluate(bars)
    assert s == "off-session", ev


def test_good_when_active_hour_normal_volume_normal_spread():
    bars = _bars_at_hour(50, hour=13)
    s, ev = liquidity_rule.evaluate(bars)
    assert s == "good", ev


def test_fair_when_one_flag_low_volume():
    bars = _bars_at_hour(50, hour=13)
    # Drop last bar volume to <40% baseline
    last = bars[-1]
    bars[-1] = Bar(timestamp=last.timestamp, open=last.open, high=last.high,
                   low=last.low, close=last.close, volume=200.0,
                   spread_pips=last.spread_pips)
    s, ev = liquidity_rule.evaluate(bars)
    assert s == "fair", ev
    assert "low_volume" in ev["flags"]


def test_fair_when_one_flag_wide_spread():
    bars = _bars_at_hour(80, hour=13, spread=0.5)
    last = bars[-1]
    bars[-1] = Bar(timestamp=last.timestamp, open=last.open, high=last.high,
                   low=last.low, close=last.close, volume=last.volume,
                   spread_pips=2.5)   # >2x median 0.5
    s, ev = liquidity_rule.evaluate(bars)
    assert s == "fair", ev
    # Hardening: canonical token is now "spread_anomaly"; legacy alias is
    # surfaced in evidence so consumers that referenced "wide_spread" still see it.
    assert "spread_anomaly" in ev["flags"]
    assert ev.get("legacy_flag_alias") == "wide_spread"


def test_poor_when_two_flags():
    bars = _bars_at_hour(80, hour=13, spread=0.5)
    last = bars[-1]
    bars[-1] = Bar(timestamp=last.timestamp, open=last.open, high=last.high,
                   low=last.low, close=last.close, volume=200.0,
                   spread_pips=2.5)
    s, ev = liquidity_rule.evaluate(bars)
    assert s == "poor", ev


def test_off_session_helper():
    on = datetime(2026, 4, 27, 13, 0, tzinfo=timezone.utc)
    off = datetime(2026, 4, 27, 23, 0, tzinfo=timezone.utc)
    assert liquidity_rule.is_off_session(off) is True
    assert liquidity_rule.is_off_session(on) is False
