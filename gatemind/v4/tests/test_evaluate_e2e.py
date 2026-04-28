"""End-to-end pipeline tests for GateMindV4.evaluate()."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from gatemind.v4 import GateMindV4, GateOutcome, TradeDirection
from gatemind.v4.gatemind_constants import (
    REASON_DIRECTIONAL_CONFLICT,
    REASON_GRADE_BELOW,
    REASON_KILL_FLAG,
    REASON_OUTSIDE_NY,
    REASON_SCHEMA_INVALID,
    REASON_UNANIMOUS_WAIT,
)

from .conftest import (
    make_brain_output_a_buy,
    make_brain_output_a_wait,
    make_brain_output_aplus_buy,
    make_brain_output_aplus_sell,
    make_brain_output_b_grade,
    make_brain_output_invalid_schema,
    make_brain_output_with_kill_flag,
    now_dst_fall_back,
    now_dst_spring_forward,
    now_in_ny_window,
    now_outside_ny_window,
)


@pytest.fixture
def gate():
    return GateMindV4()


def test_e2e_all_aplus_buy_in_window(gate):
    decision = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert decision.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert decision.direction == TradeDirection.BUY
    assert decision.trade_candidate is not None
    assert decision.trade_candidate.direction == TradeDirection.BUY


def test_e2e_all_aplus_sell_in_window(gate):
    decision = gate.evaluate(
        make_brain_output_aplus_sell("NewsMind"),
        make_brain_output_aplus_sell("MarketMind"),
        make_brain_output_aplus_sell("ChartMind"),
        now_utc=now_in_ny_window(1),
    )
    assert decision.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert decision.direction == TradeDirection.SELL


def test_e2e_outside_ny_blocks(gate):
    decision = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_outside_ny_window(),
    )
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == REASON_OUTSIDE_NY
    assert decision.trade_candidate is None


def test_e2e_dst_spring_forward_still_works(gate):
    """Spring forward day in NY morning window — must ENTER."""
    decision = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_dst_spring_forward(),
    )
    assert decision.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert decision.session_status == "in_window_morning"


def test_e2e_dst_fall_back_still_works(gate):
    decision = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_dst_fall_back(),
    )
    assert decision.gate_decision == GateOutcome.ENTER_CANDIDATE


def test_e2e_b_grade_blocks(gate):
    decision = gate.evaluate(
        make_brain_output_b_grade("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == REASON_GRADE_BELOW


def test_e2e_kill_flag_blocks(gate):
    decision = gate.evaluate(
        make_brain_output_with_kill_flag("NewsMind", "circuit_breaker"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == REASON_KILL_FLAG


def test_e2e_directional_conflict_blocks(gate):
    decision = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_sell("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == REASON_DIRECTIONAL_CONFLICT


def test_e2e_invalid_schema_blocks(gate):
    decision = gate.evaluate(
        make_brain_output_invalid_schema("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == REASON_SCHEMA_INVALID


def test_e2e_unanimous_wait_returns_wait(gate):
    decision = gate.evaluate(
        make_brain_output_a_wait("NewsMind"),
        make_brain_output_a_wait("MarketMind"),
        make_brain_output_a_wait("ChartMind"),
        now_utc=now_in_ny_window(2),
    )
    assert decision.gate_decision == GateOutcome.WAIT
    assert decision.consensus_status == "unanimous_wait"


def test_e2e_naive_now_utc_fail_closed(gate):
    decision = gate.evaluate(
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_utc=datetime(2025, 7, 15, 14, 0),  # naive — no tz
    )
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == "naive_now_utc"


def test_e2e_stateless_same_inputs_same_outputs(gate):
    inputs = (
        make_brain_output_aplus_buy("NewsMind"),
        make_brain_output_aplus_buy("MarketMind"),
        make_brain_output_aplus_buy("ChartMind"),
        now_in_ny_window(2),
    )
    a = gate.evaluate(*inputs)
    b = gate.evaluate(*inputs)
    # Same audit_id (deterministic) and same outcome
    assert a.audit_id == b.audit_id
    assert a.gate_decision == b.gate_decision
    assert a.direction == b.direction
