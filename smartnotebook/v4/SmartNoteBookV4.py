"""SmartNoteBook V4 — orchestrator (thin facade).

Public surface (only):
  SmartNoteBookV4(base_dir).record_decision_cycle(...)
  SmartNoteBookV4(base_dir).record_gate_audit(...)
  SmartNoteBookV4(base_dir).record_rejected_trade(...)
  SmartNoteBookV4(base_dir).record_shadow_outcome(...)
  SmartNoteBookV4(base_dir).record_executed_trade(...)
  SmartNoteBookV4(base_dir).record_trade_outcome(...)
  SmartNoteBookV4(base_dir).propose_lesson(...)
  SmartNoteBookV4(base_dir).activate_lesson(...)
  SmartNoteBookV4(base_dir).retire_lesson(...)
  SmartNoteBookV4(base_dir).load_active_lessons(replay_clock)
  SmartNoteBookV4(base_dir).verify_chain()

This file delegates ALL real work to:
  storage.Storage           — JSONL+SQLite persistence
  models.*Record            — frozen dataclasses with invariants
  chain_hash                — sha256 chain
  secret_redactor           — boundary redaction
  lesson_engine             — R5 future-leak prevention
  attribution               — R7 honest credit assignment

Hard rule: this file MUST NOT contain "intelligence_score" or any other
fake constant from V3. It is a routing layer, not a scoring layer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts.brain_output import BrainOutput

from smartnotebook.v4 import chain_hash as _chain
from smartnotebook.v4 import lesson_engine
from smartnotebook.v4.models import (
    BugRecord,
    DailySummaryRecord,
    DecisionCycleRecord,
    ExecutedTradeRecord,
    GateAuditRecord,
    LessonRecord,
    MindPerformanceRecord,
    RejectedTradeRecord,
    ShadowOutcomeRecord,
    TradeOutcomeRecord,
    WeeklySummaryRecord,
)
from smartnotebook.v4.notebook_constants import (
    FINAL_BLOCK,
    FINAL_ENTER,
    FINAL_WAIT,
    SESSION_MORNING,
    SESSION_MORNING_END_HOUR,
    SESSION_MORNING_START_HOUR,
    SESSION_OUTSIDE,
    SESSION_PRE_OPEN,
    SESSION_PRE_OPEN_END_HOUR,
    SESSION_PRE_OPEN_START_HOUR,
)
from smartnotebook.v4.record_types import LessonState, RecordType, ShadowStatus
from smartnotebook.v4.storage import Storage
from smartnotebook.v4.time_integrity import (
    next_sequence_id,
    now_pair,
    to_iso_utc,
    to_ny,
    utc_now,
)

_log = logging.getLogger("smartnotebook")


def _new_record_id() -> str:
    return str(uuid.uuid4())


def _classify_session(now_ny: datetime) -> str:
    """Map NY local time → session window enum string."""
    h = now_ny.hour
    if SESSION_MORNING_START_HOUR <= h < SESSION_MORNING_END_HOUR:
        return SESSION_MORNING
    if SESSION_PRE_OPEN_START_HOUR <= h < SESSION_PRE_OPEN_END_HOUR:
        return SESSION_PRE_OPEN
    return SESSION_OUTSIDE


def _brain_output_to_dict(b: Optional[BrainOutput]) -> Dict[str, Any]:
    if b is None:
        return {}
    if not isinstance(b, BrainOutput):
        return {"_invalid_schema": True, "raw": str(type(b).__name__)}
    return {
        "brain_name": b.brain_name,
        "decision": b.decision,
        "grade": b.grade.value,
        "reason": b.reason,
        "evidence": list(b.evidence),
        "data_quality": b.data_quality,
        "should_block": b.should_block,
        "risk_flags": list(b.risk_flags),
        "confidence": float(b.confidence),
        "timestamp_utc": b.timestamp_utc.isoformat(),
    }


def _gate_decision_to_dict(g: Any) -> Dict[str, Any]:
    if g is None:
        return {}
    return {
        "gate_decision": getattr(g.gate_decision, "value", str(g.gate_decision)),
        "direction": getattr(g.direction, "value", str(g.direction)),
        "audit_id": g.audit_id,
        "blocking_reason": g.blocking_reason,
        "approval_reason": g.approval_reason,
        "consensus_status": g.consensus_status,
        "grade_status": g.grade_status,
        "session_status": g.session_status,
        "risk_flag_status": g.risk_flag_status,
        "audit_trail": list(g.audit_trail),
        "model_version": g.model_version,
    }


class SmartNoteBookV4:
    """Thin orchestrator — facade over Storage + lesson_engine + chain_hash."""

    def __init__(self, base_dir: Path | str) -> None:
        self._storage = Storage(base_dir)

    @property
    def storage(self) -> Storage:
        return self._storage

    # ------------------------------------------------------------------
    def _build_chain_for(self, record_dict: Dict[str, Any], when_utc: datetime) -> str:
        """Build a TENTATIVE chain_hash so the BaseRecord can be instantiated.

        S1 — Storage.append_record now reads prev_hash and recomputes
        chain_hash atomically under its own lock. This pre-computed
        value is therefore never trusted by storage; it exists ONLY to
        satisfy BaseRecord.__post_init__ (which requires chain_hash to
        be non-empty for R2 reasons). The persisted value will be the
        atomic one storage computes inside its lock.

        Concurrent writes are no longer racy because the canonical
        chain_hash is computed inside Storage._lock from the
        freshly-read prev_hash. Pre-computation here is best-effort.
        """
        from smartnotebook.v4 import secret_redactor as _redactor
        prev_hash = self._storage.last_chain_hash_for_day(when_utc)
        record_dict["prev_hash"] = prev_hash
        for k in list(record_dict.keys()):
            if k in ("prev_hash", "chain_hash", "sequence_id"):
                continue
            record_dict[k] = _redactor.redact(record_dict[k])
        return _chain.compute_chain_hash(prev_hash, record_dict)

    # ------------------------------------------------------------------
    def record_decision_cycle(
        self,
        *,
        symbol: str,
        news_out: Optional[BrainOutput],
        market_out: Optional[BrainOutput],
        chart_out: Optional[BrainOutput],
        gate_decision: Any,
        final_status: str,
        blocking_reason: str = "",
        evidence_summary: Optional[List[str]] = None,
        risk_flags: Optional[List[str]] = None,
        data_quality_summary: Optional[Dict[str, str]] = None,
        model_versions: Optional[Dict[str, str]] = None,
        now_utc: Optional[datetime] = None,
    ) -> DecisionCycleRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        rid = _new_record_id()
        seq = next_sequence_id()

        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.DECISION_CYCLE.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": None,
            "prev_record_id": None,
            "symbol": symbol,
            "session_window": _classify_session(n),
            "newsmind_output": _brain_output_to_dict(news_out),
            "marketmind_output": _brain_output_to_dict(market_out),
            "chartmind_output": _brain_output_to_dict(chart_out),
            "gatemind_output": _gate_decision_to_dict(gate_decision),
            "final_status": final_status,
            "blocking_reason": blocking_reason,
            "evidence_summary": list(evidence_summary or []),
            "risk_flags": list(risk_flags or []),
            "data_quality_summary": dict(data_quality_summary or {}),
            "model_versions": dict(model_versions or {}),
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch

        rec = DecisionCycleRecord(
            record_id=rid,
            record_type=RecordType.DECISION_CYCLE,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=None,
            prev_record_id=None,
            prev_hash=partial["prev_hash"],
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
        self._storage.append_record(rec)
        return rec

    # ------------------------------------------------------------------
    def record_gate_audit(
        self,
        *,
        gate_decision: Any,
        decision_cycle_id: Optional[str] = None,
        now_utc: Optional[datetime] = None,
    ) -> GateAuditRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        rid = _new_record_id()
        seq = next_sequence_id()

        gd = _gate_decision_to_dict(gate_decision)
        symbol = getattr(gate_decision, "symbol", "")
        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.GATE_AUDIT.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": decision_cycle_id,
            "prev_record_id": None,
            "symbol": symbol,
            "audit_id": gd.get("audit_id", ""),
            "gate_decision": gd.get("gate_decision", ""),
            "direction": gd.get("direction", ""),
            "blocking_reason": gd.get("blocking_reason", ""),
            "approval_reason": gd.get("approval_reason", ""),
            "mind_votes": getattr(gate_decision, "mind_votes", {}) or {},
            "mind_grades": getattr(gate_decision, "mind_grades", {}) or {},
            "mind_data_quality": getattr(gate_decision, "mind_data_quality", {}) or {},
            "consensus_status": gd.get("consensus_status", ""),
            "grade_status": gd.get("grade_status", ""),
            "session_status": gd.get("session_status", ""),
            "risk_flag_status": gd.get("risk_flag_status", ""),
            "audit_trail": gd.get("audit_trail", []),
            "model_version": gd.get("model_version", ""),
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch

        rec = GateAuditRecord(
            record_id=rid,
            record_type=RecordType.GATE_AUDIT,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=decision_cycle_id,
            prev_record_id=None,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            symbol=symbol,
            audit_id=partial["audit_id"],
            gate_decision=partial["gate_decision"],
            direction=partial["direction"],
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
        self._storage.append_record(rec)
        return rec

    # ------------------------------------------------------------------
    def record_rejected_trade(
        self,
        *,
        symbol: str,
        rejection_reason: str,
        rejecting_mind: str,
        original_direction: str,
        grades: Optional[Dict[str, str]] = None,
        would_have_entered_if_rule_relaxed: str = "",
        decision_cycle_id: Optional[str] = None,
        now_utc: Optional[datetime] = None,
    ) -> RejectedTradeRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        rid = _new_record_id()
        seq = next_sequence_id()

        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.REJECTED_TRADE.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": decision_cycle_id,
            "prev_record_id": None,
            "symbol": symbol,
            "rejection_reason": rejection_reason,
            "rejecting_mind": rejecting_mind,
            "original_direction": original_direction,
            "grades": dict(grades or {}),
            "would_have_entered_if_rule_relaxed": would_have_entered_if_rule_relaxed,
            "shadow_status": ShadowStatus.PENDING.value,
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch

        rec = RejectedTradeRecord(
            record_id=rid,
            record_type=RecordType.REJECTED_TRADE,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=decision_cycle_id,
            prev_record_id=None,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            symbol=symbol,
            rejection_reason=rejection_reason,
            rejecting_mind=rejecting_mind,
            original_direction=original_direction,
            grades=partial["grades"],
            would_have_entered_if_rule_relaxed=would_have_entered_if_rule_relaxed,
            shadow_status=ShadowStatus.PENDING,
        )
        self._storage.append_record(rec)
        return rec

    # ------------------------------------------------------------------
    def record_shadow_outcome(
        self,
        *,
        rejected_trade_id: str,
        hypothetical_entry: float,
        hypothetical_exit: float,
        hypothetical_pnl: float,
        was_rejection_correct: bool,
        evidence: Optional[List[str]] = None,
        now_utc: Optional[datetime] = None,
    ) -> ShadowOutcomeRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        rid = _new_record_id()
        seq = next_sequence_id()

        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.SHADOW_OUTCOME.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": rejected_trade_id,
            "prev_record_id": None,
            "rejected_trade_id": rejected_trade_id,
            "hypothetical_entry": float(hypothetical_entry),
            "hypothetical_exit": float(hypothetical_exit),
            "hypothetical_pnl": float(hypothetical_pnl),
            "was_rejection_correct": bool(was_rejection_correct),
            "evidence": list(evidence or []),
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch
        rec = ShadowOutcomeRecord(
            record_id=rid,
            record_type=RecordType.SHADOW_OUTCOME,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=rejected_trade_id,
            prev_record_id=None,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            rejected_trade_id=rejected_trade_id,
            hypothetical_entry=partial["hypothetical_entry"],
            hypothetical_exit=partial["hypothetical_exit"],
            hypothetical_pnl=partial["hypothetical_pnl"],
            was_rejection_correct=partial["was_rejection_correct"],
            evidence=partial["evidence"],
        )
        self._storage.append_record(rec)
        return rec

    # ------------------------------------------------------------------
    def record_executed_trade(
        self,
        *,
        symbol: str,
        direction: str,
        entry_price: float,
        size: float,
        decision_cycle_id: str,
        broker_order_id: str = "",
        now_utc: Optional[datetime] = None,
    ) -> ExecutedTradeRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        rid = _new_record_id()
        seq = next_sequence_id()
        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.EXECUTED_TRADE.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": decision_cycle_id,
            "prev_record_id": None,
            "symbol": symbol,
            "direction": direction,
            "entry_price": float(entry_price),
            "size": float(size),
            "decision_cycle_id": decision_cycle_id,
            "broker_order_id": broker_order_id,
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch
        rec = ExecutedTradeRecord(
            record_id=rid,
            record_type=RecordType.EXECUTED_TRADE,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=decision_cycle_id,
            prev_record_id=None,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            symbol=symbol,
            direction=direction,
            entry_price=float(entry_price),
            size=float(size),
            decision_cycle_id=decision_cycle_id,
            broker_order_id=broker_order_id,
        )
        self._storage.append_record(rec)
        return rec

    # ------------------------------------------------------------------
    def record_trade_outcome(
        self,
        *,
        symbol: str,
        executed_trade_id: str,
        exit_price: float,
        pnl: float,
        outcome_class: str,
        direction_match: bool,
        exit_reason: str,
        now_utc: Optional[datetime] = None,
    ) -> TradeOutcomeRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        rid = _new_record_id()
        seq = next_sequence_id()
        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.TRADE_OUTCOME.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": executed_trade_id,
            "prev_record_id": None,
            "symbol": symbol,
            "executed_trade_id": executed_trade_id,
            "exit_price": float(exit_price),
            "pnl": float(pnl),
            "outcome_class": outcome_class,
            "direction_match": bool(direction_match),
            "exit_reason": exit_reason,
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch
        rec = TradeOutcomeRecord(
            record_id=rid,
            record_type=RecordType.TRADE_OUTCOME,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=executed_trade_id,
            prev_record_id=None,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            symbol=symbol,
            executed_trade_id=executed_trade_id,
            exit_price=float(exit_price),
            pnl=float(pnl),
            outcome_class=outcome_class,
            direction_match=bool(direction_match),
            exit_reason=exit_reason,
        )
        self._storage.append_record(rec)
        return rec

    # ------------------------------------------------------------------
    # Lesson lifecycle
    # ------------------------------------------------------------------
    def propose_lesson(
        self,
        *,
        lesson_id: str,
        lesson_text: str,
        affected_mind: str,
        evidence: List[str],
        source_records: List[str],
        proposed_rule_change: Dict[str, Any],
        now_utc: Optional[datetime] = None,
    ) -> LessonRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        rid = _new_record_id()
        seq = next_sequence_id()
        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.LESSON.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": None,
            "prev_record_id": None,
            "lesson_id": lesson_id,
            "source_records": list(source_records),
            "lesson_text": lesson_text,
            "affected_mind": affected_mind,
            "evidence": list(evidence),
            "proposed_rule_change": dict(proposed_rule_change),
            "state": LessonState.CANDIDATE.value,
            "allowed_from_timestamp": None,
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch
        rec = LessonRecord(
            record_id=rid,
            record_type=RecordType.LESSON,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=None,
            prev_record_id=None,
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            lesson_id=lesson_id,
            source_records=list(source_records),
            lesson_text=lesson_text,
            affected_mind=affected_mind,
            evidence=list(evidence),
            proposed_rule_change=dict(proposed_rule_change),
            state=LessonState.CANDIDATE,
            allowed_from_timestamp=None,
        )
        self._storage.append_record(rec)
        return rec

    def activate_lesson(
        self,
        *,
        lesson_id: str,
        allowed_from_timestamp: datetime,
        now_utc: Optional[datetime] = None,
    ) -> LessonRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        prior = self._latest_lesson_record(lesson_id)
        if prior is None:
            raise ValueError(f"unknown lesson_id={lesson_id}")
        rid = _new_record_id()
        seq = next_sequence_id()
        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.LESSON.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": prior["record_id"],
            "prev_record_id": prior["record_id"],
            "lesson_id": lesson_id,
            "source_records": list(prior.get("source_records", [])),
            "lesson_text": prior.get("lesson_text", ""),
            "affected_mind": prior.get("affected_mind", ""),
            "evidence": list(prior.get("evidence", [])),
            "proposed_rule_change": dict(prior.get("proposed_rule_change", {})),
            "state": LessonState.ACTIVE.value,
            "allowed_from_timestamp": to_iso_utc(allowed_from_timestamp),
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch
        rec = LessonRecord(
            record_id=rid,
            record_type=RecordType.LESSON,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=prior["record_id"],
            prev_record_id=prior["record_id"],
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            lesson_id=lesson_id,
            source_records=list(prior.get("source_records", [])),
            lesson_text=prior.get("lesson_text", ""),
            affected_mind=prior.get("affected_mind", ""),
            evidence=list(prior.get("evidence", [])),
            proposed_rule_change=dict(prior.get("proposed_rule_change", {})),
            state=LessonState.ACTIVE,
            allowed_from_timestamp=allowed_from_timestamp,
        )
        self._storage.append_record(rec)
        return rec

    def retire_lesson(
        self,
        *,
        lesson_id: str,
        now_utc: Optional[datetime] = None,
    ) -> LessonRecord:
        u = now_utc or utc_now()
        n = to_ny(u)
        prior = self._latest_lesson_record(lesson_id)
        if prior is None:
            raise ValueError(f"unknown lesson_id={lesson_id}")
        rid = _new_record_id()
        seq = next_sequence_id()
        # Preserve the prior allowed_from_timestamp on retirement so audit
        # history remains coherent. If never activated, leave None.
        afts_str = prior.get("allowed_from_timestamp")
        partial: Dict[str, Any] = {
            "record_id": rid,
            "record_type": RecordType.LESSON.value,
            "timestamp_utc": to_iso_utc(u),
            "timestamp_ny": n.isoformat(),
            "sequence_id": seq,
            "parent_record_id": prior["record_id"],
            "prev_record_id": prior["record_id"],
            "lesson_id": lesson_id,
            "source_records": list(prior.get("source_records", [])),
            "lesson_text": prior.get("lesson_text", ""),
            "affected_mind": prior.get("affected_mind", ""),
            "evidence": list(prior.get("evidence", [])),
            "proposed_rule_change": dict(prior.get("proposed_rule_change", {})),
            "state": LessonState.RETIRED.value,
            "allowed_from_timestamp": afts_str,
        }
        ch = self._build_chain_for(partial, u)
        partial["chain_hash"] = ch

        afts_dt = None
        if afts_str:
            from smartnotebook.v4.time_integrity import parse_iso_utc
            afts_dt = parse_iso_utc(afts_str) if isinstance(afts_str, str) else afts_str

        rec = LessonRecord(
            record_id=rid,
            record_type=RecordType.LESSON,
            timestamp_utc=u,
            timestamp_ny=n,
            sequence_id=seq,
            parent_record_id=prior["record_id"],
            prev_record_id=prior["record_id"],
            prev_hash=partial["prev_hash"],
            chain_hash=ch,
            lesson_id=lesson_id,
            source_records=list(prior.get("source_records", [])),
            lesson_text=prior.get("lesson_text", ""),
            affected_mind=prior.get("affected_mind", ""),
            evidence=list(prior.get("evidence", [])),
            proposed_rule_change=dict(prior.get("proposed_rule_change", {})),
            state=LessonState.RETIRED,
            allowed_from_timestamp=afts_dt,
        )
        self._storage.append_record(rec)
        return rec

    def _latest_lesson_record(self, lesson_id: str) -> Optional[Dict[str, Any]]:
        recs = [
            r for r in self._storage.query_by_type(RecordType.LESSON)
            if r.get("lesson_id") == lesson_id
        ]
        if not recs:
            return None
        return max(recs, key=lambda r: r["sequence_id"])

    def load_active_lessons(self, replay_clock: datetime) -> List[Dict[str, Any]]:
        return lesson_engine.load_active_lessons(self._storage, replay_clock)

    # ------------------------------------------------------------------
    def verify_chain(self) -> None:
        self._storage.verify_full_chain()

    def verify_chain_for_day(self, when_utc: datetime) -> None:
        self._storage.verify_chain_for_day(when_utc)
