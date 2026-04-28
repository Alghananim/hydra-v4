"""SmartNoteBook V4 — test fixtures.

Provides:
  * tmp storage path
  * BrainOutput factories (real frozen-contract instances)
  * GateDecision factory (real frozen contract)
  * Convenience builders for each record type
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root importable (Desktop\HYDRA V4)
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from zoneinfo import ZoneInfo

from contracts.brain_output import BrainGrade, BrainOutput

from smartnotebook.v4 import chain_hash as _chain
from smartnotebook.v4 import time_integrity
from smartnotebook.v4.time_integrity import to_iso_utc
from smartnotebook.v4.models import (
    BugRecord,
    DecisionCycleRecord,
    GateAuditRecord,
    LessonRecord,
    RejectedTradeRecord,
    ShadowOutcomeRecord,
)
from smartnotebook.v4.record_types import LessonState, RecordType, ShadowStatus
from smartnotebook.v4.storage import Storage
from smartnotebook.v4.time_integrity import to_iso_utc

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# storage fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def tmpdir_storage(tmp_path: Path) -> Storage:
    time_integrity.reset_sequence_counter(0)
    return Storage(tmp_path / "ledger")


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2025, 7, 15, 14, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# BrainOutput factories
# ---------------------------------------------------------------------------
def make_brain_aplus(brain_name: str, decision: str = "BUY", *, when: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=brain_name,
        decision=decision,
        grade=BrainGrade.A_PLUS,
        reason=f"{brain_name} A+ {decision}",
        evidence=[f"{brain_name}_signal_1", f"{brain_name}_signal_2"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.9,
        timestamp_utc=when or datetime.now(UTC),
    )


def make_brain_a(brain_name: str, decision: str = "BUY", *, when: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=brain_name,
        decision=decision,
        grade=BrainGrade.A,
        reason=f"{brain_name} A {decision}",
        evidence=[f"{brain_name}_signal"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.8,
        timestamp_utc=when or datetime.now(UTC),
    )


def make_brain_c(brain_name: str, decision: str = "BUY", *, when: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=brain_name,
        decision=decision,
        grade=BrainGrade.C,
        reason=f"{brain_name} C {decision}",
        evidence=[f"{brain_name}_weak"],
        data_quality="stale",
        should_block=False,
        risk_flags=[],
        confidence=0.4,
        timestamp_utc=when or datetime.now(UTC),
    )


def make_brain_wait(brain_name: str, *, when: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=brain_name,
        decision="WAIT",
        grade=BrainGrade.A,
        reason=f"{brain_name} A WAIT",
        evidence=[f"{brain_name}_neutral"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.7,
        timestamp_utc=when or datetime.now(UTC),
    )


def make_brain_block(brain_name: str, reason: str = "fail closed") -> BrainOutput:
    return BrainOutput.fail_closed(brain_name=brain_name, reason=reason)


@pytest.fixture
def mock_brain_outputs_aplus_buy(fixed_now):
    return {
        "news": make_brain_aplus("newsmind", "BUY", when=fixed_now),
        "market": make_brain_aplus("marketmind", "BUY", when=fixed_now),
        "chart": make_brain_aplus("chartmind", "BUY", when=fixed_now),
    }


@pytest.fixture
def mock_brain_outputs_aplus_sell(fixed_now):
    return {
        "news": make_brain_aplus("newsmind", "SELL", when=fixed_now),
        "market": make_brain_aplus("marketmind", "SELL", when=fixed_now),
        "chart": make_brain_aplus("chartmind", "SELL", when=fixed_now),
    }


# ---------------------------------------------------------------------------
# GateDecision factory — uses the real frozen GateDecision contract
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_gate_decision_enter_candidate(fixed_now):
    from gatemind.v4.models import (
        GateDecision,
        GateOutcome,
        TradeCandidate,
        TradeDirection,
    )
    candidate = TradeCandidate(
        symbol="EUR_USD",
        direction=TradeDirection.BUY,
        approved_by=["newsmind", "marketmind", "chartmind"],
        approval_grades={"newsmind": "A+", "marketmind": "A+", "chartmind": "A+"},
        evidence_summary=["news A+ BUY", "market A+ BUY", "chart A+ BUY"],
        risk_flags=[],
        timestamp_utc=fixed_now,
        timestamp_ny=fixed_now.astimezone(NY),
    )
    return GateDecision(
        gate_name="gatemind",
        audit_id="gm-fixture-enter",
        timestamp_utc=fixed_now,
        timestamp_ny=fixed_now.astimezone(NY),
        symbol="EUR_USD",
        gate_decision=GateOutcome.ENTER_CANDIDATE,
        direction=TradeDirection.BUY,
        blocking_reason="",
        approval_reason="all A+",
        mind_votes={"newsmind": "BUY", "marketmind": "BUY", "chartmind": "BUY"},
        mind_grades={"newsmind": "A+", "marketmind": "A+", "chartmind": "A+"},
        mind_data_quality={"newsmind": "good", "marketmind": "good", "chartmind": "good"},
        consensus_status="agree_BUY",
        grade_status="all_A_or_better",
        session_status="in_window",
        risk_flag_status="clean",
        trade_candidate=candidate,
        audit_trail=["R1_schema:PASS", "R2_consensus:PASS"],
    )


@pytest.fixture
def mock_gate_decision_block(fixed_now):
    from gatemind.v4.models import GateDecision, GateOutcome, TradeDirection
    return GateDecision(
        gate_name="gatemind",
        audit_id="gm-fixture-block",
        timestamp_utc=fixed_now,
        timestamp_ny=fixed_now.astimezone(NY),
        symbol="EUR_USD",
        gate_decision=GateOutcome.BLOCK,
        direction=TradeDirection.NONE,
        blocking_reason="schema_invalid",
        approval_reason="",
        mind_votes={},
        mind_grades={},
        mind_data_quality={},
        consensus_status="",
        grade_status="",
        session_status="",
        risk_flag_status="",
        trade_candidate=None,
        audit_trail=["R1_schema:FAIL"],
    )


# ---------------------------------------------------------------------------
# Record builders (used by tests that need direct record construction)
# ---------------------------------------------------------------------------
def _seq() -> int:
    return time_integrity.next_sequence_id()


def _build_chained_dict(partial: Dict[str, Any], prev_hash: str) -> str:
    partial["prev_hash"] = prev_hash
    return _chain.compute_chain_hash(prev_hash, partial)


def make_decision_cycle_record(
    *,
    storage: Optional[Storage] = None,
    symbol: str = "EUR_USD",
    final_status: str = "ENTER_CANDIDATE",
    blocking_reason: str = "",
    evidence: Optional[List[str]] = None,
    when: Optional[datetime] = None,
) -> DecisionCycleRecord:
    u = when or datetime.now(UTC)
    n = u.astimezone(NY)
    rid = f"dc-{_seq()}"
    seq = _seq()
    prev_hash = storage.last_chain_hash_for_day(u) if storage else _chain.first_prev_hash()
    partial = {
        "record_id": rid,
        "record_type": RecordType.DECISION_CYCLE.value,
        "timestamp_utc": to_iso_utc(u),
        "timestamp_ny": n.isoformat(),
        "sequence_id": seq,
        "parent_record_id": None,
        "prev_record_id": None,
        "symbol": symbol,
        "session_window": "pre_open_8_12",
        "newsmind_output": {"decision": "BUY"},
        "marketmind_output": {"decision": "BUY"},
        "chartmind_output": {"decision": "BUY"},
        "gatemind_output": {"gate_decision": "ENTER_CANDIDATE"},
        "final_status": final_status,
        "blocking_reason": blocking_reason,
        "evidence_summary": list(evidence or (["evidence"] if final_status == "ENTER_CANDIDATE" else [])),
        "risk_flags": [],
        "data_quality_summary": {},
        "model_versions": {},
    }
    ch = _build_chained_dict(partial, prev_hash)
    return DecisionCycleRecord(
        record_id=rid,
        record_type=RecordType.DECISION_CYCLE,
        timestamp_utc=u,
        timestamp_ny=n,
        sequence_id=seq,
        parent_record_id=None,
        prev_record_id=None,
        prev_hash=prev_hash,
        chain_hash=ch,
        symbol=symbol,
        session_window=partial["session_window"],
        newsmind_output=partial["newsmind_output"],
        marketmind_output=partial["marketmind_output"],
        chartmind_output=partial["chartmind_output"],
        gatemind_output=partial["gatemind_output"],
        final_status=final_status,
        blocking_reason=blocking_reason,
        evidence_summary=partial["evidence_summary"],
        risk_flags=partial["risk_flags"],
        data_quality_summary=partial["data_quality_summary"],
        model_versions=partial["model_versions"],
    )


def make_gate_audit_record(
    *,
    storage: Optional[Storage] = None,
    symbol: str = "EUR_USD",
    audit_id: str = "gm-test-1",
    gate_decision: str = "ENTER_CANDIDATE",
    direction: str = "BUY",
    decision_cycle_id: Optional[str] = None,
    when: Optional[datetime] = None,
) -> GateAuditRecord:
    u = when or datetime.now(UTC)
    n = u.astimezone(NY)
    rid = f"ga-{_seq()}"
    seq = _seq()
    prev_hash = storage.last_chain_hash_for_day(u) if storage else _chain.first_prev_hash()
    partial = {
        "record_id": rid,
        "record_type": RecordType.GATE_AUDIT.value,
        "timestamp_utc": to_iso_utc(u),
        "timestamp_ny": n.isoformat(),
        "sequence_id": seq,
        "parent_record_id": decision_cycle_id,
        "prev_record_id": None,
        "symbol": symbol,
        "audit_id": audit_id,
        "gate_decision": gate_decision,
        "direction": direction,
        "blocking_reason": "" if gate_decision != "BLOCK" else "test_block",
        "approval_reason": "test_approval" if gate_decision == "ENTER_CANDIDATE" else "",
        "mind_votes": {},
        "mind_grades": {},
        "mind_data_quality": {},
        "consensus_status": "",
        "grade_status": "",
        "session_status": "",
        "risk_flag_status": "",
        "audit_trail": ["R1_schema:PASS"],
        "model_version": "v4.0.0",
    }
    ch = _build_chained_dict(partial, prev_hash)
    return GateAuditRecord(
        record_id=rid,
        record_type=RecordType.GATE_AUDIT,
        timestamp_utc=u,
        timestamp_ny=n,
        sequence_id=seq,
        parent_record_id=decision_cycle_id,
        prev_record_id=None,
        prev_hash=prev_hash,
        chain_hash=ch,
        symbol=symbol,
        audit_id=audit_id,
        gate_decision=gate_decision,
        direction=direction,
        blocking_reason=partial["blocking_reason"],
        approval_reason=partial["approval_reason"],
        mind_votes=partial["mind_votes"],
        mind_grades=partial["mind_grades"],
        mind_data_quality=partial["mind_data_quality"],
        consensus_status=partial["consensus_status"],
        grade_status=partial["grade_status"],
        session_status=partial["session_status"],
        risk_flag_status=partial["risk_flag_status"],
        audit_trail=partial["audit_trail"],
        model_version=partial["model_version"],
    )


def make_rejected_trade_record(
    *,
    storage: Optional[Storage] = None,
    symbol: str = "EUR_USD",
    rejection_reason: str = "directional_conflict",
    rejecting_mind: str = "gatemind",
    original_direction: str = "BUY",
    when: Optional[datetime] = None,
) -> RejectedTradeRecord:
    u = when or datetime.now(UTC)
    n = u.astimezone(NY)
    rid = f"rt-{_seq()}"
    seq = _seq()
    prev_hash = storage.last_chain_hash_for_day(u) if storage else _chain.first_prev_hash()
    partial = {
        "record_id": rid,
        "record_type": RecordType.REJECTED_TRADE.value,
        "timestamp_utc": to_iso_utc(u),
        "timestamp_ny": n.isoformat(),
        "sequence_id": seq,
        "parent_record_id": None,
        "prev_record_id": None,
        "symbol": symbol,
        "rejection_reason": rejection_reason,
        "rejecting_mind": rejecting_mind,
        "original_direction": original_direction,
        "grades": {"newsmind": "A+", "marketmind": "A+", "chartmind": "A+"},
        "would_have_entered_if_rule_relaxed": "",
        "shadow_status": ShadowStatus.PENDING.value,
    }
    ch = _build_chained_dict(partial, prev_hash)
    return RejectedTradeRecord(
        record_id=rid,
        record_type=RecordType.REJECTED_TRADE,
        timestamp_utc=u,
        timestamp_ny=n,
        sequence_id=seq,
        parent_record_id=None,
        prev_record_id=None,
        prev_hash=prev_hash,
        chain_hash=ch,
        symbol=symbol,
        rejection_reason=rejection_reason,
        rejecting_mind=rejecting_mind,
        original_direction=original_direction,
        grades=partial["grades"],
        would_have_entered_if_rule_relaxed="",
        shadow_status=ShadowStatus.PENDING,
    )


def make_shadow_outcome_record(
    *,
    storage: Optional[Storage] = None,
    rejected_trade_id: str,
    pnl: float = -10.0,
    when: Optional[datetime] = None,
) -> ShadowOutcomeRecord:
    u = when or datetime.now(UTC)
    n = u.astimezone(NY)
    rid = f"so-{_seq()}"
    seq = _seq()
    prev_hash = storage.last_chain_hash_for_day(u) if storage else _chain.first_prev_hash()
    partial = {
        "record_id": rid,
        "record_type": RecordType.SHADOW_OUTCOME.value,
        "timestamp_utc": to_iso_utc(u),
        "timestamp_ny": n.isoformat(),
        "sequence_id": seq,
        "parent_record_id": rejected_trade_id,
        "prev_record_id": None,
        "rejected_trade_id": rejected_trade_id,
        "hypothetical_entry": 1.10,
        "hypothetical_exit": 1.099,
        "hypothetical_pnl": float(pnl),
        "was_rejection_correct": pnl < 0,
        "evidence": ["test"],
    }
    ch = _build_chained_dict(partial, prev_hash)
    return ShadowOutcomeRecord(
        record_id=rid,
        record_type=RecordType.SHADOW_OUTCOME,
        timestamp_utc=u,
        timestamp_ny=n,
        sequence_id=seq,
        parent_record_id=rejected_trade_id,
        prev_record_id=None,
        prev_hash=prev_hash,
        chain_hash=ch,
        rejected_trade_id=rejected_trade_id,
        hypothetical_entry=partial["hypothetical_entry"],
        hypothetical_exit=partial["hypothetical_exit"],
        hypothetical_pnl=partial["hypothetical_pnl"],
        was_rejection_correct=partial["was_rejection_correct"],
        evidence=partial["evidence"],
    )


def make_lesson_candidate(
    *,
    storage: Optional[Storage] = None,
    lesson_id: str = "L1",
    when: Optional[datetime] = None,
) -> LessonRecord:
    u = when or datetime.now(UTC)
    n = u.astimezone(NY)
    rid = f"ls-{_seq()}"
    seq = _seq()
    prev_hash = storage.last_chain_hash_for_day(u) if storage else _chain.first_prev_hash()
    partial = {
        "record_id": rid,
        "record_type": RecordType.LESSON.value,
        "timestamp_utc": to_iso_utc(u),
        "timestamp_ny": n.isoformat(),
        "sequence_id": seq,
        "parent_record_id": None,
        "prev_record_id": None,
        "lesson_id": lesson_id,
        "source_records": [],
        "lesson_text": "Don't trade after consecutive losses",
        "affected_mind": "marketmind",
        "evidence": ["e1"],
        "proposed_rule_change": {"type": "cooldown", "minutes": 30},
        "state": LessonState.CANDIDATE.value,
        "allowed_from_timestamp": None,
    }
    ch = _build_chained_dict(partial, prev_hash)
    return LessonRecord(
        record_id=rid,
        record_type=RecordType.LESSON,
        timestamp_utc=u,
        timestamp_ny=n,
        sequence_id=seq,
        parent_record_id=None,
        prev_record_id=None,
        prev_hash=prev_hash,
        chain_hash=ch,
        lesson_id=lesson_id,
        source_records=[],
        lesson_text=partial["lesson_text"],
        affected_mind=partial["affected_mind"],
        evidence=partial["evidence"],
        proposed_rule_change=partial["proposed_rule_change"],
        state=LessonState.CANDIDATE,
        allowed_from_timestamp=None,
    )


def make_lesson_active(
    *,
    storage: Optional[Storage] = None,
    lesson_id: str = "L1",
    allowed_from: datetime,
    when: Optional[datetime] = None,
) -> LessonRecord:
    u = when or datetime.now(UTC)
    n = u.astimezone(NY)
    rid = f"ls-{_seq()}"
    seq = _seq()
    prev_hash = storage.last_chain_hash_for_day(u) if storage else _chain.first_prev_hash()
    partial = {
        "record_id": rid,
        "record_type": RecordType.LESSON.value,
        "timestamp_utc": to_iso_utc(u),
        "timestamp_ny": n.isoformat(),
        "sequence_id": seq,
        "parent_record_id": None,
        "prev_record_id": None,
        "lesson_id": lesson_id,
        "source_records": [],
        "lesson_text": "Active lesson text",
        "affected_mind": "marketmind",
        "evidence": ["e1"],
        "proposed_rule_change": {"type": "cooldown", "minutes": 30},
        "state": LessonState.ACTIVE.value,
        "allowed_from_timestamp": to_iso_utc(allowed_from),
    }
    ch = _build_chained_dict(partial, prev_hash)
    return LessonRecord(
        record_id=rid,
        record_type=RecordType.LESSON,
        timestamp_utc=u,
        timestamp_ny=n,
        sequence_id=seq,
        parent_record_id=None,
        prev_record_id=None,
        prev_hash=prev_hash,
        chain_hash=ch,
        lesson_id=lesson_id,
        source_records=[],
        lesson_text=partial["lesson_text"],
        affected_mind=partial["affected_mind"],
        evidence=partial["evidence"],
        proposed_rule_change=partial["proposed_rule_change"],
        state=LessonState.ACTIVE,
        allowed_from_timestamp=allowed_from,
    )


@pytest.fixture
def factory():
    return {
        "decision_cycle": make_decision_cycle_record,
        "gate_audit": make_gate_audit_record,
        "rejected_trade": make_rejected_trade_record,
        "shadow_outcome": make_shadow_outcome_record,
        "lesson_candidate": make_lesson_candidate,
        "lesson_active": make_lesson_active,
        "brain_aplus": make_brain_aplus,
        "brain_a": make_brain_a,
        "brain_c": make_brain_c,
        "brain_wait": make_brain_wait,
        "brain_block": make_brain_block,
    }
