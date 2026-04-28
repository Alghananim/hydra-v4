"""HYDRA V4 — DecisionCycleResult invariants tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from zoneinfo import ZoneInfo

from gatemind.v4.models import (
    GateDecision,
    GateOutcome,
    TradeCandidate,
    TradeDirection,
)
from orchestrator.v4.decision_cycle_record import DecisionCycleResult
from orchestrator.v4.orchestrator_constants import (
    FINAL_BLOCK,
    FINAL_ENTER_CANDIDATE,
    FINAL_ORCHESTRATOR_ERROR,
    FINAL_WAIT,
)

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def _utc_now():
    return datetime(2025, 7, 15, 14, 0, 0, tzinfo=UTC)


def _ny_now():
    return _utc_now().astimezone(NY)


def _enter_gate_decision() -> GateDecision:
    u = _utc_now()
    n = _ny_now()
    cand = TradeCandidate(
        symbol="EUR_USD",
        direction=TradeDirection.BUY,
        approved_by=["NewsMind", "MarketMind", "ChartMind"],
        approval_grades={"NewsMind": "A+", "MarketMind": "A+", "ChartMind": "A+"},
        evidence_summary=["all A+"],
        risk_flags=[],
        timestamp_utc=u,
        timestamp_ny=n,
    )
    return GateDecision(
        gate_name="GateMind",
        audit_id="gm-test-01",
        timestamp_utc=u,
        timestamp_ny=n,
        symbol="EUR_USD",
        gate_decision=GateOutcome.ENTER_CANDIDATE,
        direction=TradeDirection.BUY,
        approval_reason="all_brains_unanimous_enter",
        trade_candidate=cand,
        audit_trail=["R8_enter:ENTER:BUY"],
    )


def _block_gate_decision() -> GateDecision:
    u = _utc_now()
    n = _ny_now()
    return GateDecision(
        gate_name="GateMind",
        audit_id="gm-test-02",
        timestamp_utc=u,
        timestamp_ny=n,
        symbol="EUR_USD",
        gate_decision=GateOutcome.BLOCK,
        direction=TradeDirection.NONE,
        blocking_reason="grade_below_threshold",
        audit_trail=["R3_grade:below_threshold"],
    )


def test_minimal_wait_record():
    rec = DecisionCycleResult(
        cycle_id="hyd-test-01",
        symbol="EUR_USD",
        timestamp_utc=_utc_now(),
        timestamp_ny=_ny_now(),
        session_status="in_window_morning",
        news_output=None,
        market_output=None,
        chart_output=None,
        gate_decision=None,
        decision_cycle_record_id="dcr-1",
        gate_audit_record_id="gar-1",
        final_status=FINAL_WAIT,
        final_reason="unanimous_wait",
    )
    assert rec.final_status == FINAL_WAIT


def test_enter_candidate_requires_gate_decision():
    with pytest.raises(ValueError, match="ENTER_CANDIDATE requires"):
        DecisionCycleResult(
            cycle_id="hyd-test-01",
            symbol="EUR_USD",
            timestamp_utc=_utc_now(),
            timestamp_ny=_ny_now(),
            session_status="in_window_morning",
            news_output=None,
            market_output=None,
            chart_output=None,
            gate_decision=None,  # invalid
            decision_cycle_record_id="dcr-1",
            gate_audit_record_id="gar-1",
            final_status=FINAL_ENTER_CANDIDATE,
            final_reason="approved",
        )


def test_enter_candidate_with_real_gate_decision_passes():
    gd = _enter_gate_decision()
    rec = DecisionCycleResult(
        cycle_id="hyd-test-01",
        symbol="EUR_USD",
        timestamp_utc=_utc_now(),
        timestamp_ny=_ny_now(),
        session_status="in_window_morning",
        news_output=None,
        market_output=None,
        chart_output=None,
        gate_decision=gd,
        decision_cycle_record_id="dcr-1",
        gate_audit_record_id="gar-1",
        final_status=FINAL_ENTER_CANDIDATE,
        final_reason="approved",
    )
    assert rec.is_enter_candidate()


def test_enter_candidate_with_block_gate_rejected():
    gd = _block_gate_decision()
    with pytest.raises(ValueError, match="ENTER_CANDIDATE requires"):
        DecisionCycleResult(
            cycle_id="hyd-test-01",
            symbol="EUR_USD",
            timestamp_utc=_utc_now(),
            timestamp_ny=_ny_now(),
            session_status="outside_window",
            news_output=None,
            market_output=None,
            chart_output=None,
            gate_decision=gd,
            decision_cycle_record_id="dcr-1",
            gate_audit_record_id="gar-1",
            final_status=FINAL_ENTER_CANDIDATE,
            final_reason="approved",
        )


def test_block_requires_reason():
    with pytest.raises(ValueError, match="BLOCK"):
        DecisionCycleResult(
            cycle_id="hyd-test-01",
            symbol="EUR_USD",
            timestamp_utc=_utc_now(),
            timestamp_ny=_ny_now(),
            session_status="outside_window",
            news_output=None,
            market_output=None,
            chart_output=None,
            gate_decision=_block_gate_decision(),
            decision_cycle_record_id="dcr-1",
            gate_audit_record_id="gar-1",
            final_status=FINAL_BLOCK,
            final_reason="",  # empty
        )


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="tz-aware"):
        DecisionCycleResult(
            cycle_id="hyd-test-01",
            symbol="EUR_USD",
            timestamp_utc=datetime(2025, 7, 15, 14, 0, 0),  # naive
            timestamp_ny=_ny_now(),
            session_status="x",
            news_output=None,
            market_output=None,
            chart_output=None,
            gate_decision=None,
            decision_cycle_record_id="dcr",
            gate_audit_record_id="gar",
            final_status=FINAL_WAIT,
            final_reason="x",
        )


def test_unknown_final_status_rejected():
    with pytest.raises(ValueError, match="final_status"):
        DecisionCycleResult(
            cycle_id="hyd-test-01",
            symbol="EUR_USD",
            timestamp_utc=_utc_now(),
            timestamp_ny=_ny_now(),
            session_status="x",
            news_output=None,
            market_output=None,
            chart_output=None,
            gate_decision=None,
            decision_cycle_record_id="dcr",
            gate_audit_record_id="gar",
            final_status="WHO_KNOWS",
            final_reason="x",
        )


def test_empty_symbol_rejected():
    with pytest.raises(ValueError, match="symbol"):
        DecisionCycleResult(
            cycle_id="hyd-test-01",
            symbol="",
            timestamp_utc=_utc_now(),
            timestamp_ny=_ny_now(),
            session_status="x",
            news_output=None,
            market_output=None,
            chart_output=None,
            gate_decision=None,
            decision_cycle_record_id="dcr",
            gate_audit_record_id="gar",
            final_status=FINAL_WAIT,
            final_reason="x",
        )


def test_negative_timing_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        DecisionCycleResult(
            cycle_id="hyd-test-01",
            symbol="EUR_USD",
            timestamp_utc=_utc_now(),
            timestamp_ny=_ny_now(),
            session_status="x",
            news_output=None,
            market_output=None,
            chart_output=None,
            gate_decision=None,
            decision_cycle_record_id="dcr",
            gate_audit_record_id="gar",
            final_status=FINAL_WAIT,
            final_reason="x",
            timings_ms={"news_ms": -1.0},
        )


def test_orchestrator_error_status_allowed():
    rec = DecisionCycleResult(
        cycle_id="hyd-test-01",
        symbol="EUR_USD",
        timestamp_utc=_utc_now(),
        timestamp_ny=_ny_now(),
        session_status="x",
        news_output=None,
        market_output=None,
        chart_output=None,
        gate_decision=None,
        decision_cycle_record_id="",
        gate_audit_record_id="",
        final_status=FINAL_ORCHESTRATOR_ERROR,
        final_reason="orchestrator_error:RuntimeError:boom",
        errors=["unexpected:RuntimeError:boom"],
    )
    assert rec.final_status == FINAL_ORCHESTRATOR_ERROR
    assert rec.errors == ["unexpected:RuntimeError:boom"]


def test_to_dict_preserves_keys():
    gd = _enter_gate_decision()
    rec = DecisionCycleResult(
        cycle_id="hyd-test-01",
        symbol="EUR_USD",
        timestamp_utc=_utc_now(),
        timestamp_ny=_ny_now(),
        session_status="in_window_morning",
        news_output=None,
        market_output=None,
        chart_output=None,
        gate_decision=gd,
        decision_cycle_record_id="dcr-1",
        gate_audit_record_id="gar-1",
        final_status=FINAL_ENTER_CANDIDATE,
        final_reason="approved",
    )
    d = rec.to_dict()
    assert d["cycle_id"] == "hyd-test-01"
    assert d["final_status"] == "ENTER_CANDIDATE"
    assert d["gate_decision"]["gate_decision"] == "ENTER_CANDIDATE"
    assert d["gate_decision"]["direction"] == "BUY"
