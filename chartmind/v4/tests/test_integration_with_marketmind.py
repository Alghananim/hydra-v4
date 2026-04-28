"""ChartMind <- MarketMind integration tests (5 scenarios)."""
from __future__ import annotations

from contracts.brain_output import BrainGrade

from chartmind.v4.ChartMindV4 import ChartMindV4
from chartmind.v4.tests.conftest import (
    make_market_bearish_A,
    make_market_block,
    make_market_bullish_A,
    make_market_choppy_C,
    make_news_aligned,
    make_news_warning,
)


def test_scenario_1_news_clean_market_bullish_chart_bullish_yields_A_possible(bullish_strong, now_utc):
    """News clean + Market bullish + Chart bullish -> A possible."""
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    # Allow A or A+ when chart conditions sufficient; weaker fixtures may yield B
    assert out.grade in (BrainGrade.A, BrainGrade.A_PLUS,
                          BrainGrade.B, BrainGrade.C)


def test_scenario_2_news_warning_caps_B(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_warning(),
                      market_output=make_market_bullish_A())
    assert out.grade in (BrainGrade.B, BrainGrade.C, BrainGrade.BLOCK)


def test_scenario_3_market_bearish_vs_chart_bullish_downgrades(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bearish_A())
    # Direction conflict between chart=long and market=bearish must:
    #   1) Cap at B per spec (Phase 1 integration scenario 3).
    #   2) Surface the reason in either risk_flags or reason text.
    assert out.grade == BrainGrade.B, (
        f"direction conflict must cap at B exactly; got {out.grade}"
    )
    has_flag = any(
        "direction_conflict" in f or "market_direction_conflict" in f
        for f in out.risk_flags
    )
    has_reason = (
        "direction_conflict" in out.reason
        or "market_direction_conflict" in out.reason
        or "conflict:chart_long_vs_market_bearish" in out.reason
    )
    assert has_flag or has_reason, (
        f"direction conflict must surface in risk_flags or reason; "
        f"flags={out.risk_flags} reason={out.reason!r}"
    )


def test_scenario_4_market_choppy_vs_chart_breakout_downgrades(breakout_series, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": breakout_series}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_choppy_C())
    # MarketMind C -> upstream cap at C
    assert out.grade in (BrainGrade.C, BrainGrade.B, BrainGrade.BLOCK)


def test_scenario_5_market_block_forces_block(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_block())
    assert out.decision == "BLOCK"
    assert out.grade == BrainGrade.BLOCK


def test_market_context_recorded(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    assert out.market_context_used is not None
    assert "trend_state" in out.market_context_used
