"""Price-data validator tests — missing/stale/duplicate/invalid."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from chartmind.v4 import price_data_validator as pdv
from chartmind.v4.tests.conftest import make_bullish_strong_bars


def test_no_bars_is_missing(now_utc):
    status, warns = pdv.assess([], now_utc=now_utc)
    assert status == "missing"
    assert "no_bars" in warns


def test_too_few_bars_is_missing(now_utc, bullish_strong):
    status, warns = pdv.assess(bullish_strong[:5], now_utc=now_utc)
    assert status == "missing"
    assert any(w.startswith("too_few_bars") for w in warns)


def test_good_bars_pass(now_utc, bullish_strong):
    status, warns = pdv.assess(bullish_strong, now_utc=now_utc)
    assert status == "good"


def test_naive_now_is_broken(bullish_strong):
    naive = datetime(2026, 4, 27)
    status, warns = pdv.assess(bullish_strong, now_utc=naive)
    assert status == "broken"


def test_duplicate_timestamps_is_broken(now_utc, bullish_strong):
    bars = list(bullish_strong)
    # Construct a fresh duplicate by copying constructor args
    from marketmind.v4.models import Bar
    last = bars[-1]
    dupe = Bar(
        timestamp=last.timestamp,
        open=last.open,
        high=last.high,
        low=last.low,
        close=last.close,
        volume=last.volume,
        spread_pips=last.spread_pips,
    )
    bars.append(dupe)
    status, warns = pdv.assess(bars, now_utc=now_utc)
    assert status == "broken"


def test_non_monotonic_is_broken(now_utc, bullish_strong):
    from marketmind.v4.models import Bar
    bars = list(bullish_strong)
    # Insert a bar with an EARLIER timestamp than its predecessor
    ts_back = bars[-1].timestamp - timedelta(minutes=30)
    bars.append(Bar(timestamp=ts_back, open=1.10, high=1.11, low=1.09,
                    close=1.10, volume=1000.0, spread_pips=0.5))
    status, warns = pdv.assess(bars, now_utc=now_utc)
    assert status == "broken"


def test_stale_last_bar(bullish_strong):
    far_future = bullish_strong[-1].timestamp + timedelta(hours=10)
    status, warns = pdv.assess(bullish_strong, now_utc=far_future)
    assert status == "stale"


def test_future_bar_is_broken(now_utc, bullish_strong):
    # now_utc earlier than last bar timestamp
    early = bullish_strong[0].timestamp - timedelta(hours=1)
    status, warns = pdv.assess(bullish_strong, now_utc=early)
    assert status == "broken"
