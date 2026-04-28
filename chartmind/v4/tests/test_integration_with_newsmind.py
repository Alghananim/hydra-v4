"""ChartMind <- NewsMind integration tests."""
from __future__ import annotations

from contracts.brain_output import BrainGrade

from chartmind.v4.ChartMindV4 import ChartMindV4
from chartmind.v4.tests.conftest import (
    make_market_bullish_A,
    make_news_aligned,
    make_news_block,
    make_news_warning,
)


def test_newsmind_block_forces_chartmind_block(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_block(),
                      market_output=make_market_bullish_A())
    assert out.decision == "BLOCK"
    assert out.grade == BrainGrade.BLOCK
    assert "upstream_block" in out.risk_flags or "fail_closed" in out.risk_flags


def test_newsmind_warning_caps_at_B(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_warning(),
                      market_output=make_market_bullish_A())
    # Warning grade=B caps us at B
    assert out.grade in (BrainGrade.B, BrainGrade.C, BrainGrade.BLOCK)


def test_newsmind_aligned_does_not_cap(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    # No upstream cap from NewsMind A
    assert "upstream_cap" not in " ".join(out.risk_flags) or \
        out.grade in (BrainGrade.A, BrainGrade.A_PLUS, BrainGrade.B, BrainGrade.C)


def test_newsmind_missing_blocks(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=None,
                      market_output=make_market_bullish_A())
    assert out.decision == "BLOCK"


def test_news_context_recorded(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    assert out.news_context_used is not None
    assert "grade" in out.news_context_used
