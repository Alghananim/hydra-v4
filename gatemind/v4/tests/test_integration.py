"""GateMind V4 integration tests — 10 scenarios as specified in the brief.

Each scenario constructs real BrainOutput instances (the same contract that
NewsMind / MarketMind / ChartMind emit in production) and asserts the gate
outcome.
"""

from __future__ import annotations

import pytest

from gatemind.v4 import GateMindV4, GateOutcome, TradeDirection
from gatemind.v4.gatemind_constants import (
    REASON_DIRECTIONAL_CONFLICT,
    REASON_GRADE_BELOW,
    REASON_INCOMPLETE_AGREEMENT,
    REASON_KILL_FLAG,
    REASON_OUTSIDE_NY,
    REASON_SCHEMA_INVALID,
    REASON_UNANIMOUS_WAIT,
)

from .conftest import (
    make_brain_output_a_buy,
    make_brain_output_a_sell,
    make_brain_output_a_wait,
    make_brain_output_aplus_buy,
    make_brain_output_aplus_sell,
    make_brain_output_b_grade,
    make_brain_output_invalid_schema,
    make_brain_output_with_kill_flag,
    now_in_ny_window,
    now_outside_ny_window,
)


@pytest.fixture
def gate():
    return GateMindV4()


# -------------------- Scenario 1 --------------------
def test_scenario_1_all_aplus_buy_in_ny(gate):
    d = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert d.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert d.direction == TradeDirection.BUY
    assert d.consensus_status == "unanimous_buy"
    assert d.grade_status == "all_a_plus"
    assert d.trade_candidate is not None


# -------------------- Scenario 2 --------------------
def test_scenario_2_all_a_sell_in_ny(gate):
    d = gate.evaluate(
        make_brain_output_a_sell("NewsMind"),
        make_brain_output_a_sell("MarketMind"),
        make_brain_output_a_sell("ChartMind"),
        now_utc=now_in_ny_window(1),
    )
    assert d.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert d.direction == TradeDirection.SELL
    assert d.grade_status == "all_a_or_better"


# -------------------- Scenario 3 --------------------
def test_scenario_3_mixed_grades_buy(gate):
    d = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_a_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert d.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert d.direction == TradeDirection.BUY
    assert d.grade_status == "all_a_or_better"


# -------------------- Scenario 4 --------------------
def test_scenario_4_all_wait(gate):
    d = gate.evaluate(
        make_brain_output_a_wait("NewsMind"),
        make_brain_output_a_wait("MarketMind"),
        make_brain_output_a_wait("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert d.gate_decision == GateOutcome.WAIT
    assert d.consensus_status == "unanimous_wait"


# -------------------- Scenario 5 --------------------
def test_scenario_5_2buy_1wait_blocks(gate):
    d = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_a_wait("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert d.gate_decision == GateOutcome.BLOCK
    assert d.blocking_reason == REASON_INCOMPLETE_AGREEMENT


# -------------------- Scenario 6 --------------------
def test_scenario_6_2buy_1sell_directional_conflict(gate):
    d = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_sell("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert d.gate_decision == GateOutcome.BLOCK
    assert d.blocking_reason == REASON_DIRECTIONAL_CONFLICT


# -------------------- Scenario 7 --------------------
def test_scenario_7_all_buy_one_b_grade(gate):
    d = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_b_grade("ChartMind", decision="BUY"),
        now_utc=now_in_ny_window(2),
    )
    assert d.gate_decision == GateOutcome.BLOCK
    assert d.blocking_reason == REASON_GRADE_BELOW


# -------------------- Scenario 8 --------------------
def test_scenario_8_chartmind_invalid_schema(gate):
    d = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_invalid_schema("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert d.gate_decision == GateOutcome.BLOCK
    assert d.blocking_reason == REASON_SCHEMA_INVALID


# -------------------- Scenario 9 --------------------
def test_scenario_9_kill_flag_in_news(gate):
    d = gate.evaluate(
        make_brain_output_with_kill_flag("NewsMind", "news_blackout"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert d.gate_decision == GateOutcome.BLOCK
    assert d.blocking_reason == REASON_KILL_FLAG


# -------------------- Scenario 10 --------------------
def test_scenario_10_all_aplus_buy_outside_ny(gate):
    d = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_outside_ny_window(),
    )
    assert d.gate_decision == GateOutcome.BLOCK
    assert d.blocking_reason == REASON_OUTSIDE_NY
