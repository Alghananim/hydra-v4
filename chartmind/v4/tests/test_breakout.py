"""Breakout / fake-breakout tests."""
from __future__ import annotations

from marketmind.v4 import indicators

from chartmind.v4 import breakout_detector as bd


def test_real_breakout_detected(breakout_series):
    atr = indicators.atr(breakout_series)
    # Resistance is the level the fixture put at 1.1030
    r = bd.detect_breakout(breakout_series, level=1.1030, atr_value=atr,
                           side="long", confirm_index=60)
    assert r.is_breakout, r.reason
    assert not r.is_fake


def test_same_bar_fake_detected(fake_breakout_series):
    atr = indicators.atr(fake_breakout_series)
    r = bd.detect_breakout(fake_breakout_series, level=1.1030, atr_value=atr,
                           side="long", confirm_index=60)
    assert not r.is_breakout
    assert r.is_fake
    assert "same_bar_fake" in r.reason


def test_no_breakout_in_quiet_range(ranging):
    atr = indicators.atr(ranging)
    last_close = ranging[-1].close
    r = bd.detect_breakout(ranging, level=last_close + 5 * atr, atr_value=atr,
                           side="long")
    assert not r.is_breakout


def test_zero_atr_returns_no_breakout(breakout_series):
    r = bd.detect_breakout(breakout_series, level=1.10, atr_value=0.0,
                           side="long")
    assert not r.is_breakout
    assert r.reason == "no_inputs"


def test_invalid_side_returns_no_breakout(breakout_series):
    atr = indicators.atr(breakout_series)
    r = bd.detect_breakout(breakout_series, level=1.10, atr_value=atr, side="weird")
    assert not r.is_breakout


def test_short_breakout_mirror():
    """Construct downward breakout and confirm short side detection."""
    from datetime import datetime, timedelta, timezone
    from marketmind.v4.models import Bar
    base = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    bars = []
    # 30 quiet bars around 1.1000
    for i in range(30):
        c = 1.1000 + (0.0001 if i % 2 else -0.0001)
        bars.append(Bar(timestamp=base + timedelta(minutes=15 * i),
                        open=1.1000, high=1.1003, low=1.0997, close=c,
                        volume=1000.0, spread_pips=0.5))
    # Big down breakout
    bars.append(Bar(timestamp=base + timedelta(minutes=15 * 30),
                    open=1.0998, high=1.0999, low=1.0950,
                    close=1.0955,  # well below
                    volume=2000.0, spread_pips=0.5))
    atr = indicators.atr(bars)
    r = bd.detect_breakout(bars, level=1.0995, atr_value=atr, side="short",
                           confirm_index=30)
    assert r.is_breakout, r.reason


def test_find_recent_breakout_scans_window(breakout_series):
    atr = indicators.atr(breakout_series)
    r = bd.find_recent_breakout(breakout_series, level=1.1030,
                                atr_value=atr, side="long", lookback=30)
    assert r.is_breakout
