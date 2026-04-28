"""test_evaluate_e2e.py — full pipeline through SmartNoteBookV4."""

from __future__ import annotations

from datetime import timedelta, timezone

import pytest

from smartnotebook.v4 import SmartNoteBookV4
from smartnotebook.v4.record_types import RecordType


def test_record_decision_cycle_writes_record(tmp_path, fixed_now,
                                              mock_brain_outputs_aplus_buy,
                                              mock_gate_decision_enter_candidate):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    rec = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=mock_brain_outputs_aplus_buy["news"],
        market_out=mock_brain_outputs_aplus_buy["market"],
        chart_out=mock_brain_outputs_aplus_buy["chart"],
        gate_decision=mock_gate_decision_enter_candidate,
        final_status="ENTER_CANDIDATE",
        evidence_summary=["all A+", "consensus"],
        now_utc=fixed_now,
    )
    assert rec.final_status == "ENTER_CANDIDATE"
    assert rec.chain_hash
    rows = nb.storage.query_by_type(RecordType.DECISION_CYCLE)
    assert len(rows) == 1


def test_full_trade_lifecycle(tmp_path, fixed_now,
                               mock_brain_outputs_aplus_buy,
                               mock_gate_decision_enter_candidate):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    dc = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=mock_brain_outputs_aplus_buy["news"],
        market_out=mock_brain_outputs_aplus_buy["market"],
        chart_out=mock_brain_outputs_aplus_buy["chart"],
        gate_decision=mock_gate_decision_enter_candidate,
        final_status="ENTER_CANDIDATE",
        evidence_summary=["consensus A+"],
        now_utc=fixed_now,
    )
    ga = nb.record_gate_audit(
        gate_decision=mock_gate_decision_enter_candidate,
        decision_cycle_id=dc.record_id,
        now_utc=fixed_now,
    )
    et = nb.record_executed_trade(
        symbol="EUR_USD",
        direction="BUY",
        entry_price=1.10,
        size=1000,
        decision_cycle_id=dc.record_id,
        now_utc=fixed_now + timedelta(seconds=1),
    )
    to = nb.record_trade_outcome(
        symbol="EUR_USD",
        executed_trade_id=et.record_id,
        exit_price=1.105,
        pnl=50.0,
        outcome_class="WIN",
        direction_match=True,
        exit_reason="tp_hit",
        now_utc=fixed_now + timedelta(hours=2),
    )
    nb.verify_chain()
    assert nb.storage.get_by_id(to.record_id) is not None


def test_lesson_propose_activate_retire(tmp_path, fixed_now):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    cand = nb.propose_lesson(
        lesson_id="L1",
        lesson_text="cool down after 3 losses",
        affected_mind="marketmind",
        evidence=["e1"],
        source_records=[],
        proposed_rule_change={"type": "cooldown"},
        now_utc=fixed_now,
    )
    assert cand.state.value == "CANDIDATE"
    activated = nb.activate_lesson(
        lesson_id="L1",
        allowed_from_timestamp=fixed_now,
        now_utc=fixed_now + timedelta(seconds=1),
    )
    assert activated.state.value == "ACTIVE"
    retired = nb.retire_lesson(lesson_id="L1", now_utc=fixed_now + timedelta(seconds=2))
    assert retired.state.value == "RETIRED"


def test_chain_verify_after_full_cycle(tmp_path, fixed_now,
                                        mock_brain_outputs_aplus_buy,
                                        mock_gate_decision_enter_candidate):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    dc = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=mock_brain_outputs_aplus_buy["news"],
        market_out=mock_brain_outputs_aplus_buy["market"],
        chart_out=mock_brain_outputs_aplus_buy["chart"],
        gate_decision=mock_gate_decision_enter_candidate,
        final_status="ENTER_CANDIDATE",
        evidence_summary=["c"],
        now_utc=fixed_now,
    )
    nb.record_gate_audit(
        gate_decision=mock_gate_decision_enter_candidate,
        decision_cycle_id=dc.record_id,
        now_utc=fixed_now,
    )
    nb.verify_chain()  # must not raise
