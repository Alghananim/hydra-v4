"""News integration tests."""
from __future__ import annotations

from contracts.brain_output import BrainGrade
from marketmind.v4 import news_integration
from marketmind.v4.tests.conftest import (
    make_news_aligned, make_news_block, make_news_silent, make_news_warning,
)


def test_block_propagates():
    ctx = news_integration.map_news_output(make_news_block())
    assert ctx.news_state == "block"
    assert ctx.news_grade_cap == BrainGrade.BLOCK


def test_warning_caps_at_b():
    ctx = news_integration.map_news_output(make_news_warning())
    assert ctx.news_state == "warning"
    assert ctx.news_grade_cap == BrainGrade.B


def test_silent_c_grade_caps_at_b():
    # NewsMind 'C' (silent / weak) is treated as warning
    ctx = news_integration.map_news_output(make_news_silent())
    assert ctx.news_state == "warning"
    assert ctx.news_grade_cap == BrainGrade.B


def test_aligned_no_cap():
    ctx = news_integration.map_news_output(make_news_aligned())
    assert ctx.news_state == "aligned"
    assert ctx.news_grade_cap is None


def test_none_input():
    ctx = news_integration.map_news_output(None)
    assert ctx.news_state == "no_news"
    assert ctx.news_grade_cap is None
    assert ctx.snapshot == {"present": False}


def test_snapshot_carries_facts():
    ctx = news_integration.map_news_output(make_news_warning())
    assert ctx.snapshot["brain_name"] == "newsmind"
    assert ctx.snapshot["grade"] == "B"
    assert "unverified_source" in ctx.snapshot["risk_flags"]
