"""End-to-end ChartMindV4.evaluate() tests."""
from __future__ import annotations

from contracts.brain_output import BrainGrade

from chartmind.v4.ChartMindV4 import ChartMindV4
from chartmind.v4.chart_thresholds import EVIDENCE_KEYS
from chartmind.v4.tests.conftest import (
    make_market_bullish_A,
    make_news_aligned,
)


def test_evaluate_bullish_returns_assessment(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate(
        pair="EURUSD",
        bars_by_tf={"M15": bullish_strong},
        now_utc=now_utc,
        news_output=make_news_aligned(),
        market_output=make_market_bullish_A(),
    )
    assert out.brain_name == "chartmind"
    assert out.atr_value > 0
    assert out.entry_zone["low"] < out.entry_zone["high"]


def test_evaluate_no_bars_blocks(now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": []}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    assert out.decision == "BLOCK"
    assert out.grade == BrainGrade.BLOCK


def test_evaluate_missing_news_forces_block(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=None,  # missing -> block
                      market_output=make_market_bullish_A())
    assert out.decision == "BLOCK"


def test_evaluate_emits_real_atr(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    # Real ATR should be far from any "round" V3-hardcoded number
    assert out.atr_value not in (0.0, 1.0, 0.001, 0.0002)
    assert out.indicator_snapshot["atr"] == out.atr_value


def test_evaluate_band_is_band_not_scalar(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    assert out.entry_zone["high"] - out.entry_zone["low"] > 0


def test_evaluate_stale_data_caps_at_B(bullish_strong):
    from datetime import datetime, timedelta, timezone
    far_future = bullish_strong[-1].timestamp + timedelta(hours=10)
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=far_future,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    # Stale -> BrainOutput contract forbids A/A+
    assert out.grade in (BrainGrade.B, BrainGrade.C, BrainGrade.BLOCK)


def test_evaluate_keys_for_assessment(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    d = out.to_dict()
    for key in ("entry_zone", "invalidation_level", "stop_reference",
                "target_reference", "trend_structure", "volatility_state",
                "atr_value", "key_levels", "setup_type", "indicator_snapshot",
                "news_context_used", "market_context_used"):
        assert key in d, f"missing {key}"


def test_naive_now_fail_closes(bullish_strong):
    from datetime import datetime
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong},
                      now_utc=datetime(2026, 4, 28),  # naive
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    assert out.decision == "BLOCK"


def test_e2e_chartmind_can_emit_a_plus(bullish_strong, now_utc):
    """Hardening C3: prove the A+ ladder is REACHABLE end-to-end.

    Drive ChartMindV4.evaluate with the (newly tuned) bullish_strong fixture
    and clean upstream (NewsMind A, MarketMind A bullish) and assert the
    grade lands at A or A+ — proving the additive evidence ladder is not
    statistically capped at C/B.

    Acceptance per Hardening spec: A is acceptable proof; A+ is the goal.
    """
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    assert out.grade in (BrainGrade.A_PLUS, BrainGrade.A), (
        f"A+ ladder unreachable: grade={out.grade.value} reason={out.reason!r} "
        f"trend={out.trend_structure} setup={out.setup_type}"
    )
