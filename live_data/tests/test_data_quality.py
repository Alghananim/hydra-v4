"""Tests for data_quality_checker."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from live_data.data_quality_checker import (
    InvalidCandleError,
    check_quality,
    is_acceptable,
)


def _candle(t: str, *, complete=True, volume=100, bid=1.1004, ask=1.1006):
    return {
        "time": t,
        "complete": complete,
        "volume": volume,
        "mid": {"c": "1.1005"},
        "bid": {"c": f"{bid:.5f}"},
        "ask": {"c": f"{ask:.5f}"},
    }


def _ts(i, step_min=15):
    base = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    t = base + timedelta(minutes=i * step_min)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


def test_no_issues_clean_run():
    candles = [_candle(_ts(i)) for i in range(2000)]
    r = check_quality(candles, "EUR_USD", "M15")
    assert r["total_bars"] == 2000
    assert r["duplicate_ts_count"] == 0
    assert r["missing_bars"] == 0
    assert r["non_complete_bars"] == 0
    assert r["stale_bars_volume_zero"] == 0


def test_detects_duplicates():
    candles = [_candle(_ts(0))] * 5 + [_candle(_ts(i)) for i in range(1, 100)]
    r = check_quality(candles, "EUR_USD", "M15")
    assert r["duplicate_ts_count"] == 4


def test_detects_gap():
    """Gap of 5 hours in M15 should register as missing bars."""
    candles = [_candle(_ts(i)) for i in range(10)]
    candles += [_candle(_ts(30 + i)) for i in range(10)]  # skip 20 candles
    r = check_quality(candles, "EUR_USD", "M15")
    assert r["missing_bars"] >= 19
    assert r["gaps_minutes_max"] >= 15 * 20


def test_detects_stale_volume():
    candles = [_candle(_ts(i), volume=0) for i in range(50)]
    r = check_quality(candles, "EUR_USD", "M15")
    assert r["stale_bars_volume_zero"] == 50


def test_detects_non_complete():
    candles = [_candle(_ts(i), complete=False) for i in range(10)]
    r = check_quality(candles, "EUR_USD", "M15")
    assert r["non_complete_bars"] == 10


def test_spread_avg_eurusd():
    """Spread of 2 pips on EUR/USD."""
    candles = [_candle(_ts(i), bid=1.1004, ask=1.1006) for i in range(100)]
    r = check_quality(candles, "EUR_USD", "M15")
    # 0.0002 / 0.0001 = 2 pips
    assert abs(r["spread_avg_pips"] - 2.0) < 0.01


def test_spread_avg_usdjpy():
    """USD/JPY pip is 0.01 — verify pair-aware pip math."""
    candles = [_candle(_ts(i), bid=150.00, ask=150.02) for i in range(100)]
    r = check_quality(candles, "USD_JPY", "M15")
    # 0.02 / 0.01 = 2 pips
    assert abs(r["spread_avg_pips"] - 2.0) < 0.01


def test_weekend_gaps_separated():
    """A 48-hour weekend gap is NOT counted as missing-bars."""
    candles = [_candle(_ts(i)) for i in range(10)]
    # Insert a candle 48 hours later (weekend) — should be classified as weekend gap
    later = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc) + timedelta(hours=48) + timedelta(minutes=15 * 9)
    candles.append(_candle(later.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")))
    r = check_quality(candles, "EUR_USD", "M15")
    assert r["weekend_gaps_detected"] >= 1


def test_acceptable_clean():
    candles = [_candle(_ts(i)) for i in range(2000)]
    r = check_quality(candles, "EUR_USD", "M15")
    ok, reasons = is_acceptable(r)
    assert ok, reasons


def test_unacceptable_too_few_bars():
    candles = [_candle(_ts(i)) for i in range(100)]
    r = check_quality(candles, "EUR_USD", "M15")
    ok, reasons = is_acceptable(r)
    assert not ok
    assert any("too few" in x for x in reasons)


def test_unacceptable_duplicates():
    candles = [_candle(_ts(0))] * 3 + [_candle(_ts(i)) for i in range(1, 1500)]
    r = check_quality(candles, "EUR_USD", "M15")
    ok, reasons = is_acceptable(r)
    assert not ok
    assert any("duplicates" in x for x in reasons)


# ---------------------------------------------------------------------------
# H1: NaN/Inf bars must be REJECTED at the quality-check boundary
# ---------------------------------------------------------------------------
def test_nan_close_rejected_at_quality_check():
    """A bar with mid.c='NaN' must raise InvalidCandleError, NOT silently
    propagate a NaN spread/avg into the report."""
    bar = _candle(_ts(0))
    bar["mid"] = {"c": "NaN"}
    candles = [bar] + [_candle(_ts(i)) for i in range(1, 50)]
    with pytest.raises(InvalidCandleError):
        check_quality(candles, "EUR_USD", "M15")


def test_positive_inf_close_rejected_at_quality_check():
    bar = _candle(_ts(0))
    bar["mid"] = {"c": "Infinity"}
    candles = [bar] + [_candle(_ts(i)) for i in range(1, 50)]
    with pytest.raises(InvalidCandleError):
        check_quality(candles, "EUR_USD", "M15")


def test_negative_inf_close_rejected_at_quality_check():
    bar = _candle(_ts(0))
    bar["mid"] = {"c": "-Infinity"}
    candles = [bar] + [_candle(_ts(i)) for i in range(1, 50)]
    with pytest.raises(InvalidCandleError):
        check_quality(candles, "EUR_USD", "M15")


def test_nan_bid_rejected_at_quality_check():
    bar = _candle(_ts(0))
    bar["bid"] = {"c": "NaN"}
    candles = [bar] + [_candle(_ts(i)) for i in range(1, 50)]
    with pytest.raises(InvalidCandleError):
        check_quality(candles, "EUR_USD", "M15")


# ---------------------------------------------------------------------------
# H8: defense-in-depth — is_acceptable refuses a non-finite spread_avg_pips
# ---------------------------------------------------------------------------
def test_is_acceptable_refuses_nan_spread_avg():
    fake_report = {
        "total_bars": 5000,
        "duplicate_ts_count": 0,
        "missing_bars": 0,
        "non_complete_bars": 0,
        "spread_avg_pips": float("nan"),
    }
    ok, reasons = is_acceptable(fake_report)
    assert not ok
    assert any("spread_not_finite" in r for r in reasons)


def test_is_acceptable_refuses_inf_spread_avg():
    fake_report = {
        "total_bars": 5000,
        "duplicate_ts_count": 0,
        "missing_bars": 0,
        "non_complete_bars": 0,
        "spread_avg_pips": math.inf,
    }
    ok, reasons = is_acceptable(fake_report)
    assert not ok
    assert any("spread_not_finite" in r for r in reasons)


def test_is_acceptable_passes_with_none_spread_avg():
    """When no bid/ask data exists, spread_avg_pips is None — that's OK."""
    fake_report = {
        "total_bars": 5000,
        "duplicate_ts_count": 0,
        "missing_bars": 0,
        "non_complete_bars": 0,
        "spread_avg_pips": None,
    }
    ok, reasons = is_acceptable(fake_report)
    assert ok, reasons
