"""test_integration.py — 10 scenarios with real BrainOutput + GateDecision."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from contracts.brain_output import BrainGrade, BrainOutput
from gatemind.v4.models import GateDecision, GateOutcome, TradeCandidate, TradeDirection

from smartnotebook.v4 import SmartNoteBookV4
from smartnotebook.v4.record_types import RecordType

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def _make_news(decision="BUY", grade=BrainGrade.A_PLUS, when=None):
    return BrainOutput(
        brain_name="newsmind", decision=decision, grade=grade,
        reason="news", evidence=["calendar clean"], data_quality="good",
        should_block=False, risk_flags=[], confidence=0.9,
        timestamp_utc=when or datetime.now(UTC),
    )


def _make_market(decision="BUY", grade=BrainGrade.A_PLUS, when=None, dq="good"):
    return BrainOutput(
        brain_name="marketmind", decision=decision, grade=grade,
        reason="market", evidence=["trend up"], data_quality=dq,
        should_block=False, risk_flags=[], confidence=0.85,
        timestamp_utc=when or datetime.now(UTC),
    )


def _make_chart(decision="BUY", grade=BrainGrade.A_PLUS, when=None):
    return BrainOutput(
        brain_name="chartmind", decision=decision, grade=grade,
        reason="chart", evidence=["breakout"], data_quality="good",
        should_block=False, risk_flags=[], confidence=0.88,
        timestamp_utc=when or datetime.now(UTC),
    )


def _make_enter_decision(when, direction=TradeDirection.BUY, symbol="EUR_USD"):
    candidate = TradeCandidate(
        symbol=symbol,
        direction=direction,
        approved_by=["newsmind", "marketmind", "chartmind"],
        approval_grades={"newsmind": "A+", "marketmind": "A+", "chartmind": "A+"},
        evidence_summary=["all A+"],
        risk_flags=[],
        timestamp_utc=when,
        timestamp_ny=when.astimezone(NY),
    )
    return GateDecision(
        gate_name="gatemind",
        audit_id=f"gm-test-{when.isoformat()}",
        timestamp_utc=when,
        timestamp_ny=when.astimezone(NY),
        symbol=symbol,
        gate_decision=GateOutcome.ENTER_CANDIDATE,
        direction=direction,
        approval_reason="all A+",
        mind_votes={"newsmind": direction.value, "marketmind": direction.value, "chartmind": direction.value},
        mind_grades={"newsmind": "A+", "marketmind": "A+", "chartmind": "A+"},
        mind_data_quality={"newsmind": "good", "marketmind": "good", "chartmind": "good"},
        consensus_status=f"agree_{direction.value}",
        grade_status="all_A_or_better",
        session_status="in_window",
        risk_flag_status="clean",
        trade_candidate=candidate,
        audit_trail=["R1_schema:PASS"],
    )


def _make_block_decision(when, reason="schema_invalid", symbol="EUR_USD"):
    return GateDecision(
        gate_name="gatemind",
        audit_id=f"gm-block-{when.isoformat()}",
        timestamp_utc=when,
        timestamp_ny=when.astimezone(NY),
        symbol=symbol,
        gate_decision=GateOutcome.BLOCK,
        direction=TradeDirection.NONE,
        blocking_reason=reason,
        approval_reason="",
        mind_votes={},
        mind_grades={},
        mind_data_quality={},
        consensus_status="",
        grade_status="",
        session_status="",
        risk_flag_status="",
        trade_candidate=None,
        audit_trail=[f"R1_schema:FAIL:{reason}"],
    )


def _make_wait_decision(when, symbol="EUR_USD"):
    return GateDecision(
        gate_name="gatemind",
        audit_id=f"gm-wait-{when.isoformat()}",
        timestamp_utc=when,
        timestamp_ny=when.astimezone(NY),
        symbol=symbol,
        gate_decision=GateOutcome.WAIT,
        direction=TradeDirection.NONE,
        blocking_reason="",
        approval_reason="",
        mind_votes={"newsmind": "WAIT"},
        mind_grades={"newsmind": "A"},
        mind_data_quality={"newsmind": "good"},
        consensus_status="all_wait",
        grade_status="all_A_or_better",
        session_status="in_window",
        risk_flag_status="clean",
        trade_candidate=None,
        audit_trail=["R1_schema:PASS", "R2_consensus:WAIT"],
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
def test_scenario_1_all_aplus_buy_enter(tmp_path, fixed_now):
    nb = SmartNoteBookV4(tmp_path / "s1")
    rec = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=_make_news("BUY", when=fixed_now),
        market_out=_make_market("BUY", when=fixed_now),
        chart_out=_make_chart("BUY", when=fixed_now),
        gate_decision=_make_enter_decision(fixed_now),
        final_status="ENTER_CANDIDATE",
        evidence_summary=["all A+ BUY"],
        now_utc=fixed_now,
    )
    assert rec.final_status == "ENTER_CANDIDATE"


def test_scenario_2_all_a_sell_enter(tmp_path, fixed_now):
    nb = SmartNoteBookV4(tmp_path / "s2")
    rec = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=_make_news("SELL", grade=BrainGrade.A, when=fixed_now),
        market_out=_make_market("SELL", grade=BrainGrade.A, when=fixed_now),
        chart_out=_make_chart("SELL", grade=BrainGrade.A, when=fixed_now),
        gate_decision=_make_enter_decision(fixed_now, direction=TradeDirection.SELL),
        final_status="ENTER_CANDIDATE",
        evidence_summary=["all A SELL"],
        now_utc=fixed_now,
    )
    assert rec.final_status == "ENTER_CANDIDATE"


def test_scenario_3_news_missing_block(tmp_path, fixed_now):
    nb = SmartNoteBookV4(tmp_path / "s3")
    rec = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=None,  # missing
        market_out=_make_market("BUY", when=fixed_now),
        chart_out=_make_chart("BUY", when=fixed_now),
        gate_decision=_make_block_decision(fixed_now, reason="schema_invalid"),
        final_status="BLOCK",
        blocking_reason="schema_invalid",
        now_utc=fixed_now,
    )
    assert rec.final_status == "BLOCK"
    assert rec.blocking_reason == "schema_invalid"


def test_scenario_4_market_choppy_grade_block(tmp_path, fixed_now):
    nb = SmartNoteBookV4(tmp_path / "s4")
    rec = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=_make_news("BUY", when=fixed_now),
        market_out=_make_market("BUY", grade=BrainGrade.C, when=fixed_now, dq="stale"),
        chart_out=_make_chart("BUY", when=fixed_now),
        gate_decision=_make_block_decision(fixed_now, reason="grade_below_floor"),
        final_status="BLOCK",
        blocking_reason="grade_below_floor",
        now_utc=fixed_now,
    )
    assert rec.final_status == "BLOCK"


def test_scenario_5_chart_strong_directional_conflict_rejected_trade(tmp_path, fixed_now):
    nb = SmartNoteBookV4(tmp_path / "s5")
    dc = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=_make_news("BUY", when=fixed_now),
        market_out=_make_market("WAIT", grade=BrainGrade.A, when=fixed_now),
        chart_out=_make_chart("SELL", when=fixed_now),
        gate_decision=_make_block_decision(fixed_now, reason="directional_conflict"),
        final_status="BLOCK",
        blocking_reason="directional_conflict",
        now_utc=fixed_now,
    )
    rt = nb.record_rejected_trade(
        symbol="EUR_USD",
        rejection_reason="directional_conflict",
        rejecting_mind="gatemind",
        original_direction="SELL",
        decision_cycle_id=dc.record_id,
        now_utc=fixed_now,
    )
    assert rt.shadow_status.value == "PENDING"


def test_scenario_6_all_wait(tmp_path, fixed_now):
    nb = SmartNoteBookV4(tmp_path / "s6")
    news = BrainOutput(
        brain_name="newsmind", decision="WAIT", grade=BrainGrade.A,
        reason="wait", evidence=["calendar"], data_quality="good",
        should_block=False, risk_flags=[], confidence=0.7, timestamp_utc=fixed_now,
    )
    market = BrainOutput(
        brain_name="marketmind", decision="WAIT", grade=BrainGrade.A,
        reason="wait", evidence=["range"], data_quality="good",
        should_block=False, risk_flags=[], confidence=0.7, timestamp_utc=fixed_now,
    )
    chart = BrainOutput(
        brain_name="chartmind", decision="WAIT", grade=BrainGrade.A,
        reason="wait", evidence=["consolidation"], data_quality="good",
        should_block=False, risk_flags=[], confidence=0.7, timestamp_utc=fixed_now,
    )
    rec = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=news, market_out=market, chart_out=chart,
        gate_decision=_make_wait_decision(fixed_now),
        final_status="WAIT",
        now_utc=fixed_now,
    )
    assert rec.final_status == "WAIT"


def test_scenario_7_outside_window_block(tmp_path):
    """05:00 NY local on a weekday — outside both 3-5 and 8-12 windows."""
    out_ny = datetime(2025, 7, 15, 6, 30, 0, tzinfo=NY)
    out_utc = out_ny.astimezone(UTC)
    nb = SmartNoteBookV4("/tmp/disregarded")  # use tmp_path
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        nb = SmartNoteBookV4(td)
        rec = nb.record_decision_cycle(
            symbol="EUR_USD",
            news_out=_make_news("BUY", when=out_utc),
            market_out=_make_market("BUY", when=out_utc),
            chart_out=_make_chart("BUY", when=out_utc),
            gate_decision=_make_block_decision(out_utc, reason="outside_window"),
            final_status="BLOCK",
            blocking_reason="outside_window",
            now_utc=out_utc,
        )
        assert rec.session_window == "outside"


def test_scenario_8_claude_downgrade_simulated(tmp_path, fixed_now):
    """A grade was downgraded due to evidence concerns. Capture in evidence_summary."""
    nb = SmartNoteBookV4(tmp_path / "s8")
    # NewsMind was originally A+ but Claude downgraded to A in the audit trail
    news = _make_news("BUY", grade=BrainGrade.A, when=fixed_now)
    rec = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=news,
        market_out=_make_market("BUY", when=fixed_now),
        chart_out=_make_chart("BUY", when=fixed_now),
        gate_decision=_make_enter_decision(fixed_now),
        final_status="ENTER_CANDIDATE",
        evidence_summary=["news downgraded by claude_review", "consensus BUY"],
        now_utc=fixed_now,
    )
    assert any("downgrad" in e.lower() for e in rec.evidence_summary)


def test_scenario_9_rejected_then_shadow_outcome(tmp_path, fixed_now):
    """Rejected trade later gets a shadow outcome linked via parent_record_id."""
    nb = SmartNoteBookV4(tmp_path / "s9")
    dc = nb.record_decision_cycle(
        symbol="EUR_USD",
        news_out=_make_news("BUY", when=fixed_now),
        market_out=_make_market("WAIT", grade=BrainGrade.A, when=fixed_now),
        chart_out=_make_chart("BUY", when=fixed_now),
        gate_decision=_make_block_decision(fixed_now, reason="directional_conflict"),
        final_status="BLOCK",
        blocking_reason="directional_conflict",
        now_utc=fixed_now,
    )
    rt = nb.record_rejected_trade(
        symbol="EUR_USD",
        rejection_reason="directional_conflict",
        rejecting_mind="gatemind",
        original_direction="BUY",
        decision_cycle_id=dc.record_id,
        now_utc=fixed_now,
    )
    later = fixed_now + timedelta(days=2)
    so = nb.record_shadow_outcome(
        rejected_trade_id=rt.record_id,
        hypothetical_entry=1.10,
        hypothetical_exit=1.095,
        hypothetical_pnl=-50.0,
        was_rejection_correct=True,
        evidence=["price retraced"],
        now_utc=later,
    )
    assert so.parent_record_id == rt.record_id
    children = nb.storage.query_by_parent(rt.record_id)
    assert any(c["record_id"] == so.record_id for c in children)


def test_scenario_10_disk_full_during_record(tmp_path, fixed_now,
                                              mock_brain_outputs_aplus_buy,
                                              mock_gate_decision_enter_candidate):
    nb = SmartNoteBookV4(tmp_path / "s10")
    from pathlib import Path
    real_path_open = Path.open

    def boom(self, *a, **kw):
        if str(self).endswith(".jsonl") and ((a and a[0] == "a") or kw.get("mode") == "a"):
            raise OSError(28, "No space left on device")
        return real_path_open(self, *a, **kw)

    from smartnotebook.v4.error_handling import LedgerWriteError
    import unittest.mock
    with unittest.mock.patch.object(Path, "open", boom):
        with pytest.raises(LedgerWriteError):
            nb.record_decision_cycle(
                symbol="EUR_USD",
                news_out=mock_brain_outputs_aplus_buy["news"],
                market_out=mock_brain_outputs_aplus_buy["market"],
                chart_out=mock_brain_outputs_aplus_buy["chart"],
                gate_decision=mock_gate_decision_enter_candidate,
                final_status="ENTER_CANDIDATE",
                evidence_summary=["e"],
                now_utc=fixed_now,
            )
