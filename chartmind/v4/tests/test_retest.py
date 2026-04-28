"""Retest detection tests — 3-10 bar window, rejection wick, continuation."""
from __future__ import annotations

from marketmind.v4 import indicators

from chartmind.v4 import retest_detector as rd


def test_retest_detected_in_window(retest_series):
    atr = indicators.atr(retest_series)
    r = rd.detect_retest(retest_series, breakout_index=50,
                         level=1.1030, atr_value=atr, side="long")
    assert r.is_retest, r.reason
    assert 53 <= r.bar_index <= 60


def test_no_retest_when_no_window_yet(retest_series):
    atr = indicators.atr(retest_series)
    # Use a breakout index too late; no future bars
    r = rd.detect_retest(retest_series, breakout_index=len(retest_series) - 1,
                         level=1.1030, atr_value=atr, side="long")
    assert not r.is_retest


def test_retest_zero_atr_no_retest(retest_series):
    r = rd.detect_retest(retest_series, breakout_index=50,
                         level=1.1030, atr_value=0.0, side="long")
    assert not r.is_retest


def test_retest_invalid_side(retest_series):
    atr = indicators.atr(retest_series)
    r = rd.detect_retest(retest_series, breakout_index=50,
                         level=1.1030, atr_value=atr, side="meta")
    assert not r.is_retest


def test_no_retest_when_bars_run_away(breakout_series):
    """Plain breakout with continuation but no pullback to level should fail retest test."""
    atr = indicators.atr(breakout_series)
    r = rd.detect_retest(breakout_series, breakout_index=60,
                         level=1.1030, atr_value=atr, side="long")
    assert not r.is_retest
