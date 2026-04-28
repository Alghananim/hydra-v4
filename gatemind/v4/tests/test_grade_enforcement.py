"""Tests for grade enforcement — A/A+ only ever passes."""

from __future__ import annotations

import pytest

from gatemind.v4 import GateMindV4, GateOutcome
from gatemind.v4.gatemind_constants import REASON_GRADE_BELOW

from .conftest import (
    make_brain_output_a_buy,
    make_brain_output_aplus_buy,
    make_brain_output_b_grade,
    now_in_ny_window,
)


@pytest.fixture
def gate():
    return GateMindV4()


def test_b_grade_anywhere_blocks(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_b_grade("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == REASON_GRADE_BELOW


def test_b_grade_in_news_blocks(gate):
    n = make_brain_output_b_grade("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.BLOCK


def test_b_grade_in_market_blocks(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_b_grade("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.BLOCK


def test_all_aplus_buy_enters(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert decision.grade_status == "all_a_plus"


def test_mixed_a_and_aplus_enters(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_a_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert decision.grade_status == "all_a_or_better"


def test_b_with_buy_can_never_enter(gate):
    """Property: even with kill flags absent and unanimous direction, B blocks."""
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_b_grade("ChartMind", decision="BUY")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision != GateOutcome.ENTER_CANDIDATE
