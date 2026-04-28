"""Tests for trade_candidate_builder + GateDecision invariants on candidates."""

from __future__ import annotations

import pytest

from gatemind.v4 import GateMindV4, GateOutcome, TradeCandidate, TradeDirection
from gatemind.v4.models import GateDecision
from gatemind.v4.trade_candidate_builder import build_trade_candidate

from .conftest import (
    make_brain_output_a_buy,
    make_brain_output_aplus_buy,
    make_brain_output_aplus_sell,
    make_brain_output_with_warning_flag,
    now_in_ny_window,
)


def test_build_buy_candidate_has_required_fields():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    now_utc = now_in_ny_window(2)
    cand = build_trade_candidate(
        symbol="EUR_USD",
        direction=TradeDirection.BUY,
        news=n,
        market=m,
        chart=c,
        warning_flags=[],
        now_utc=now_utc,
    )
    assert cand.symbol == "EUR_USD"
    assert cand.direction == TradeDirection.BUY
    assert cand.approved_by == ["NewsMind", "MarketMind", "ChartMind"]
    assert cand.approval_grades["NewsMind"] == "A+"
    assert cand.timestamp_utc == now_utc
    assert cand.timestamp_ny.utcoffset() is not None


def test_build_rejects_none_direction():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    with pytest.raises(ValueError):
        build_trade_candidate(
            symbol="EUR_USD",
            direction=TradeDirection.NONE,
            news=n, market=m, chart=c,
            warning_flags=[], now_utc=now_in_ny_window(2),
        )


def test_evidence_gathered_and_capped():
    """Evidence list should include items from each brain (capped per-brain)."""
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    cand = build_trade_candidate(
        symbol="EUR_USD",
        direction=TradeDirection.BUY,
        news=n, market=m, chart=c,
        warning_flags=[], now_utc=now_in_ny_window(2),
    )
    assert any(line.startswith("NewsMind:") for line in cand.evidence_summary)
    assert any(line.startswith("MarketMind:") for line in cand.evidence_summary)
    assert any(line.startswith("ChartMind:") for line in cand.evidence_summary)


def test_warning_flags_propagate_to_candidate():
    gate = GateMindV4()
    n = make_brain_output_with_warning_flag("NewsMind", "low_liquidity")
    m = make_brain_output_with_warning_flag("MarketMind", "spread_anomaly")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.ENTER_CANDIDATE
    flags = decision.trade_candidate.risk_flags
    assert any("low_liquidity" in f for f in flags)
    assert any("spread_anomaly" in f for f in flags)


def test_gate_decision_invariant_enter_requires_candidate():
    """GateDecision raises if ENTER_CANDIDATE but trade_candidate is None."""
    with pytest.raises(ValueError):
        GateDecision(
            gate_decision=GateOutcome.ENTER_CANDIDATE,
            direction=TradeDirection.BUY,
            trade_candidate=None,
        )


def test_gate_decision_invariant_block_must_not_have_candidate():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    cand = build_trade_candidate(
        symbol="EUR_USD",
        direction=TradeDirection.BUY,
        news=n, market=m, chart=c,
        warning_flags=[], now_utc=now_in_ny_window(2),
    )
    with pytest.raises(ValueError):
        GateDecision(
            gate_decision=GateOutcome.BLOCK,
            direction=TradeDirection.NONE,
            blocking_reason="x",
            trade_candidate=cand,
        )


def test_gate_decision_enter_requires_direction():
    """ENTER_CANDIDATE with direction NONE must raise."""
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    cand = build_trade_candidate(
        symbol="EUR_USD",
        direction=TradeDirection.BUY,
        news=n, market=m, chart=c,
        warning_flags=[], now_utc=now_in_ny_window(2),
    )
    with pytest.raises(ValueError):
        GateDecision(
            gate_decision=GateOutcome.ENTER_CANDIDATE,
            direction=TradeDirection.NONE,
            trade_candidate=cand,
        )
