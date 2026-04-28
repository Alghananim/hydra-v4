"""HYDRA V4 — GateMind verdict is FINAL.

We verify that whatever GateMind returns — ENTER_CANDIDATE, WAIT, BLOCK —
the orchestrator's final_status mirrors it 1:1. The orchestrator MUST
NOT relax a BLOCK or upgrade a WAIT.

We use a "marionette GateMind" that returns each verdict in turn and
verify the orchestrator's final_status follows.
"""

from __future__ import annotations

from datetime import timezone

import pytest
from zoneinfo import ZoneInfo

from gatemind.v4.models import (
    GateDecision,
    GateOutcome,
    TradeCandidate,
    TradeDirection,
)
from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
from orchestrator.v4.orchestrator_constants import (
    FINAL_BLOCK,
    FINAL_ENTER_CANDIDATE,
    FINAL_WAIT,
)
from orchestrator.v4.tests.conftest import (
    MockChartMind,
    MockMarketMind,
    MockNewsMind,
)
from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4

NY = ZoneInfo("America/New_York")


def _make_gate(outcome, when_utc, *, direction=TradeDirection.NONE,
               approval_reason="", blocking_reason=""):
    n = when_utc.astimezone(NY)
    candidate = None
    if outcome == GateOutcome.ENTER_CANDIDATE:
        candidate = TradeCandidate(
            symbol="EUR_USD",
            direction=direction,
            approved_by=["NewsMind", "MarketMind", "ChartMind"],
            approval_grades={"NewsMind": "A+", "MarketMind": "A+", "ChartMind": "A+"},
            evidence_summary=["test"],
            risk_flags=[],
            timestamp_utc=when_utc,
            timestamp_ny=n,
        )
    if outcome == GateOutcome.BLOCK and not blocking_reason:
        blocking_reason = "marionette_block"
    return GateDecision(
        gate_name="GateMind",
        audit_id=f"gm-test-{outcome.value}",
        timestamp_utc=when_utc,
        timestamp_ny=n,
        symbol="EUR_USD",
        gate_decision=outcome,
        direction=direction,
        approval_reason=approval_reason,
        blocking_reason=blocking_reason,
        trade_candidate=candidate,
        audit_trail=[f"R8:{outcome.value}"],
    )


class FakeGateMind:
    def __init__(self, gd: GateDecision):
        self._gd = gd
        self.calls = 0

    def evaluate(self, *a, **kw):
        self.calls += 1
        return self._gd


def _build(tmp_path, gate, bundle):
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=MockNewsMind(bundle["news"]),
        marketmind=MockMarketMind(bundle["market"]),
        chartmind=MockChartMind(bundle["chart"]),
        gatemind=gate,
        smartnotebook=SmartNoteBookV4(tmp_path / "ledger"),
    )
    return orch


def test_gate_enter_yields_final_enter(
    tmp_path, bundle_aplus_buy, bars_input
):
    gate = FakeGateMind(_make_gate(
        GateOutcome.ENTER_CANDIDATE, bundle_aplus_buy["now_utc"],
        direction=TradeDirection.BUY, approval_reason="approved",
    ))
    orch = _build(tmp_path, gate, bundle_aplus_buy)
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_ENTER_CANDIDATE


def test_gate_wait_yields_final_wait(
    tmp_path, bundle_aplus_buy, bars_input
):
    gate = FakeGateMind(_make_gate(
        GateOutcome.WAIT, bundle_aplus_buy["now_utc"],
    ))
    orch = _build(tmp_path, gate, bundle_aplus_buy)
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_WAIT


def test_gate_block_yields_final_block(
    tmp_path, bundle_aplus_buy, bars_input
):
    gate = FakeGateMind(_make_gate(
        GateOutcome.BLOCK, bundle_aplus_buy["now_utc"],
        blocking_reason="marionette_block_reason",
    ))
    orch = _build(tmp_path, gate, bundle_aplus_buy)
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_BLOCK
    assert "marionette_block_reason" in res.final_reason


def test_orchestrator_does_not_mutate_gate_decision(
    tmp_path, bundle_aplus_buy, bars_input
):
    """GateDecision is frozen — assert the same object reaches the
    DecisionCycleResult unchanged in field values."""
    gd = _make_gate(
        GateOutcome.BLOCK, bundle_aplus_buy["now_utc"],
        blocking_reason="x_reason",
    )
    gate = FakeGateMind(gd)
    orch = _build(tmp_path, gate, bundle_aplus_buy)
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.gate_decision is gd
    assert res.gate_decision.blocking_reason == "x_reason"
    assert res.gate_decision.gate_decision == GateOutcome.BLOCK
