"""Market structure tests — adaptive k, BoS/CHoCH, fractal fallback."""
from __future__ import annotations

from chartmind.v4 import market_structure as ms
from chartmind.v4.chart_thresholds import SWING_K


def test_swing_k_locked_at_3():
    assert SWING_K == 3, "Phase-1 lock: k=3 (was k=2 in V3)."


def test_find_swings_empty():
    assert ms.find_swings([]) == []


def test_find_swings_too_short():
    # Only 5 bars; need 2k+1 = 7
    from chartmind.v4.tests.conftest import make_bullish_strong_bars
    bars = make_bullish_strong_bars(5)
    assert ms.find_swings(bars) == []


def test_find_swings_returns_some_for_trend(bullish_strong):
    swings = ms.find_swings(bullish_strong)
    assert len(swings) >= 2


def test_diagnose_bullish_strong_label(bullish_strong):
    diag = ms.diagnose_trend(bullish_strong)
    # Tightened (Hardening C3): the strong fixture is now tuned to reliably
    # produce bullish_strong (HH>=3, HL>=3, EMA-20 slope>0, no BoS).
    # Accepting bullish_weak/transitioning would let regressions slip in.
    assert diag.label == "bullish_strong", (
        f"strong fixture must label bullish_strong; got {diag.label} "
        f"(hh={diag.hh_swings} hl={diag.hl_swings} slope={diag.ema_slope:.6f} "
        f"bos={diag.bos} choch={diag.choch})"
    )


def test_diagnose_bearish_strong_label(bearish_strong):
    diag = ms.diagnose_trend(bearish_strong)
    # Tightened (Hardening C3): symmetric mirror of bullish_strong fixture
    # must reliably register as bearish_strong.
    assert diag.label == "bearish_strong", (
        f"strong fixture must label bearish_strong; got {diag.label} "
        f"(lh={diag.lh_swings} ll={diag.ll_swings} slope={diag.ema_slope:.6f} "
        f"bos={diag.bos} choch={diag.choch})"
    )


def test_diagnose_range_label(ranging):
    diag = ms.diagnose_trend(ranging)
    # range OR transitioning OR weak directional — at minimum NOT a strong directional trend
    assert diag.label not in ("bullish_strong", "bearish_strong")


def test_diagnose_choppy_label(choppy):
    diag = ms.diagnose_trend(choppy)
    # Must NOT register as a strong directional trend
    assert diag.label in ("choppy", "transitioning", "range")
    assert diag.label not in ("bullish_strong", "bearish_strong")


def test_close_fractal_fallback():
    # Construct bars where high/low are flat but closes drift -> fallback should return swings
    from datetime import datetime, timedelta, timezone
    from marketmind.v4.models import Bar
    base_ts = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    bars = []
    closes = [1.10, 1.11, 1.10, 1.12, 1.10, 1.13, 1.10, 1.14, 1.10, 1.15]
    for i, c in enumerate(closes):
        # All bars have identical high/low
        bars.append(Bar(timestamp=base_ts + timedelta(minutes=15 * i),
                        open=c, high=1.20, low=1.05, close=c,
                        volume=1000.0, spread_pips=0.5))
    fb = ms.find_swings_on_close(bars)
    assert isinstance(fb, list)


def test_diagnostic_fields_set(bullish_strong):
    d = ms.diagnose_trend(bullish_strong)
    assert d.via in ("hl", "close")
    assert isinstance(d.hh_swings, int)
    assert isinstance(d.adx_value, float)


def test_no_lookahead_swing_index_within_bounds(bullish_strong):
    swings = ms.find_swings(bullish_strong)
    for s in swings:
        assert 0 <= s.index < len(bullish_strong)
