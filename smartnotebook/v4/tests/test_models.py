"""test_models.py — record dataclass invariants."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from smartnotebook.v4 import chain_hash as _chain
from smartnotebook.v4.models import (
    BugRecord,
    DecisionCycleRecord,
    LessonRecord,
    RejectedTradeRecord,
)
from smartnotebook.v4.record_types import LessonState, RecordType, ShadowStatus

UTC = timezone.utc
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")


def _now():
    u = datetime.now(UTC)
    return u, u.astimezone(NY)


def _ch(partial, prev_hash="0" * 64):
    partial["prev_hash"] = prev_hash
    return _chain.compute_chain_hash(prev_hash, partial)


def test_chain_hash_required_R2(fixed_now):
    """R2: chain_hash empty must raise."""
    u, n = fixed_now, fixed_now.astimezone(NY)
    with pytest.raises(ValueError, match="chain_hash required"):
        DecisionCycleRecord(
            record_id="r1",
            record_type=RecordType.DECISION_CYCLE,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=1,
            chain_hash="",  # empty -> raise
            symbol="EUR_USD",
            final_status="WAIT",
        )


def test_decision_cycle_block_requires_reason(fixed_now):
    u, n = fixed_now, fixed_now.astimezone(NY)
    partial = {
        "record_id": "r1",
        "record_type": RecordType.DECISION_CYCLE.value,
        "timestamp_utc": u.isoformat(),
        "timestamp_ny": n.isoformat(),
        "sequence_id": 1,
        "parent_record_id": None,
        "prev_record_id": None,
        "symbol": "EUR_USD",
        "session_window": "outside",
        "newsmind_output": {},
        "marketmind_output": {},
        "chartmind_output": {},
        "gatemind_output": {},
        "final_status": "BLOCK",
        "blocking_reason": "",  # missing => raise
        "evidence_summary": [],
        "risk_flags": [],
        "data_quality_summary": {},
        "model_versions": {},
    }
    ch = _ch(partial)
    with pytest.raises(ValueError, match="BLOCK requires blocking_reason"):
        DecisionCycleRecord(
            record_id="r1",
            record_type=RecordType.DECISION_CYCLE,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=1,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            symbol="EUR_USD",
            session_window="outside",
            final_status="BLOCK",
            blocking_reason="",
        )


def test_decision_cycle_enter_requires_evidence(fixed_now):
    u, n = fixed_now, fixed_now.astimezone(NY)
    partial = {
        "record_id": "r1",
        "record_type": RecordType.DECISION_CYCLE.value,
        "timestamp_utc": u.isoformat(),
        "timestamp_ny": n.isoformat(),
        "sequence_id": 1,
        "parent_record_id": None,
        "prev_record_id": None,
        "symbol": "EUR_USD",
        "session_window": "morning_3_5",
        "newsmind_output": {},
        "marketmind_output": {},
        "chartmind_output": {},
        "gatemind_output": {},
        "final_status": "ENTER_CANDIDATE",
        "blocking_reason": "",
        "evidence_summary": [],  # empty => raise
        "risk_flags": [],
        "data_quality_summary": {},
        "model_versions": {},
    }
    ch = _ch(partial)
    with pytest.raises(ValueError, match="ENTER_CANDIDATE requires evidence_summary"):
        DecisionCycleRecord(
            record_id="r1",
            record_type=RecordType.DECISION_CYCLE,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=1,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            symbol="EUR_USD",
            session_window="morning_3_5",
            final_status="ENTER_CANDIDATE",
            evidence_summary=[],
        )


def test_lesson_active_requires_allowed_from(fixed_now):
    u, n = fixed_now, fixed_now.astimezone(NY)
    partial = {
        "record_id": "L1",
        "record_type": RecordType.LESSON.value,
        "timestamp_utc": u.isoformat(),
        "timestamp_ny": n.isoformat(),
        "sequence_id": 1,
        "parent_record_id": None,
        "prev_record_id": None,
        "lesson_id": "L1",
        "source_records": [],
        "lesson_text": "x",
        "affected_mind": "newsmind",
        "evidence": ["e"],
        "proposed_rule_change": {},
        "state": LessonState.ACTIVE.value,
        "allowed_from_timestamp": None,
    }
    ch = _ch(partial)
    with pytest.raises(ValueError, match="ACTIVE lesson requires allowed_from_timestamp"):
        LessonRecord(
            record_id="L1",
            record_type=RecordType.LESSON,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=1,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            lesson_id="L1",
            lesson_text="x",
            affected_mind="newsmind",
            evidence=["e"],
            state=LessonState.ACTIVE,
            allowed_from_timestamp=None,
        )


def test_rejected_trade_requires_buy_or_sell(fixed_now):
    u, n = fixed_now, fixed_now.astimezone(NY)
    partial = {
        "record_id": "rt",
        "record_type": RecordType.REJECTED_TRADE.value,
        "timestamp_utc": u.isoformat(),
        "timestamp_ny": n.isoformat(),
        "sequence_id": 1,
        "parent_record_id": None,
        "prev_record_id": None,
        "symbol": "EUR_USD",
        "rejection_reason": "directional_conflict",
        "rejecting_mind": "gatemind",
        "original_direction": "WAIT",  # invalid
        "grades": {},
        "would_have_entered_if_rule_relaxed": "",
        "shadow_status": ShadowStatus.PENDING.value,
    }
    ch = _ch(partial)
    with pytest.raises(ValueError, match="original_direction"):
        RejectedTradeRecord(
            record_id="rt",
            record_type=RecordType.REJECTED_TRADE,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=1,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            symbol="EUR_USD",
            rejection_reason="directional_conflict",
            rejecting_mind="gatemind",
            original_direction="WAIT",
        )


def test_record_is_frozen(fixed_now, factory, tmpdir_storage):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        rec.symbol = "BTC_USD"  # type: ignore


def test_bug_record_severity_invariant(fixed_now):
    u, n = fixed_now, fixed_now.astimezone(NY)
    partial = {
        "record_id": "b1",
        "record_type": RecordType.BUG.value,
        "timestamp_utc": u.isoformat(),
        "timestamp_ny": n.isoformat(),
        "sequence_id": 1,
        "parent_record_id": None,
        "prev_record_id": None,
        "severity": "weird",
        "component": "x",
        "description": "y",
        "context": {},
    }
    ch = _ch(partial)
    with pytest.raises(ValueError, match="severity"):
        BugRecord(
            record_id="b1",
            record_type=RecordType.BUG,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=1,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            severity="weird",
            component="x",
            description="y",
        )
