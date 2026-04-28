"""HYDRA V4 — final DecisionCycleResult.

This is the artefact returned by HydraOrchestratorV4.run_cycle. It is a
*frozen* snapshot — once minted it cannot be mutated. Downstream
consumers (router, dashboard, trade-routing) read this and only this.

Invariants (enforced in __post_init__):

  * final_status in VALID_FINAL_STATUSES
  * cycle_id non-empty
  * symbol non-empty
  * timestamp_utc tz-aware UTC
  * timestamp_ny tz-aware (any non-UTC zone is fine; usually
    America/New_York)
  * If final_status == ENTER_CANDIDATE:
        gate_decision is not None AND
        gate_decision.gate_decision.value == "ENTER_CANDIDATE"
  * If final_status == BLOCK:
        final_reason must be non-empty
  * timings_ms keys are strings, values are non-negative floats

The DecisionCycleResult does NOT carry the raw bars, the SmartNoteBook
chain hash, or any broker-side fields. It carries every BrainOutput
snapshot in full so the cycle can be replayed in audit.

Note (Fix O3 — ledger / DCR final_status divergence):
    The DECISION_CYCLE record written to SmartNoteBook accepts
    `final_status` only in {ENTER_CANDIDATE, WAIT, BLOCK} (the V4
    ledger contract is frozen). When the orchestrator stamps
    `final_status=ORCHESTRATOR_ERROR` on this DecisionCycleResult, the
    matching ledger row is recorded as BLOCK with `blocking_reason`
    starting with ``orchestrator_error:`` (see
    ``ORCHESTRATOR_ERROR_PREFIX``). Auditors who need to find every
    ORCHESTRATOR_ERROR cycle can either:
      * Read DecisionCycleResult.final_status (preferred for live
        callers), or
      * Query SmartNoteBook DECISION_CYCLE rows and grep
        blocking_reason for ``orchestrator_error:`` (for offline audit).
    The `errors` field on this result also surfaces the same marker for
    downstream serialisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from contracts.brain_output import BrainOutput
from orchestrator.v4.orchestrator_constants import (
    FINAL_BLOCK,
    FINAL_ENTER_CANDIDATE,
    VALID_FINAL_STATUSES,
)


@dataclass(frozen=True)
class DecisionCycleResult:
    """Frozen result of one orchestrator cycle."""

    cycle_id: str
    symbol: str
    timestamp_utc: datetime
    timestamp_ny: datetime
    session_status: str

    # Brain outputs (any may be None on orchestrator-level error)
    news_output: Optional[BrainOutput]
    market_output: Optional[BrainOutput]
    chart_output: Optional[BrainOutput]
    # gate_decision is a GateDecision (typed Any to avoid circular import)
    gate_decision: Optional[Any]

    # SmartNoteBook linkage
    decision_cycle_record_id: str
    gate_audit_record_id: str

    # Final state
    final_status: str
    final_reason: str

    # Optional
    errors: List[str] = field(default_factory=list)
    timings_ms: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # cycle_id non-empty
        if not self.cycle_id or not self.cycle_id.strip():
            raise ValueError("cycle_id must be non-empty")
        # symbol non-empty
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        # tz-aware UTC
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be tz-aware UTC")
        if self.timestamp_utc.utcoffset() is None or \
                self.timestamp_utc.utcoffset().total_seconds() != 0:
            raise ValueError(
                f"timestamp_utc must be UTC, got offset "
                f"{self.timestamp_utc.utcoffset()}"
            )
        if self.timestamp_ny.tzinfo is None:
            raise ValueError("timestamp_ny must be tz-aware")
        # final_status vocab
        if self.final_status not in VALID_FINAL_STATUSES:
            raise ValueError(
                f"final_status must be one of {VALID_FINAL_STATUSES}, "
                f"got {self.final_status!r}"
            )
        # ENTER_CANDIDATE invariant — must come from a real gate ENTER
        if self.final_status == FINAL_ENTER_CANDIDATE:
            if self.gate_decision is None:
                raise ValueError(
                    "final_status=ENTER_CANDIDATE requires gate_decision"
                )
            inner = getattr(self.gate_decision, "gate_decision", None)
            inner_val = getattr(inner, "value", None)
            if inner_val != "ENTER_CANDIDATE":
                raise ValueError(
                    "final_status=ENTER_CANDIDATE requires "
                    "gate_decision.gate_decision=ENTER_CANDIDATE, "
                    f"got {inner_val!r}"
                )
        # BLOCK invariant — must give a reason
        if self.final_status == FINAL_BLOCK and not (
            self.final_reason and self.final_reason.strip()
        ):
            raise ValueError("BLOCK final_status requires non-empty final_reason")
        # timings_ms type guard
        if not isinstance(self.timings_ms, dict):
            raise TypeError("timings_ms must be a dict")
        for k, v in self.timings_ms.items():
            if not isinstance(k, str):
                raise TypeError(f"timings_ms key must be str, got {type(k)!r}")
            if not isinstance(v, (int, float)):
                raise TypeError(
                    f"timings_ms[{k!r}] must be numeric, got {type(v)!r}"
                )
            if float(v) < 0.0:
                raise ValueError(
                    f"timings_ms[{k!r}] must be non-negative, got {v}"
                )

    # ------------------------------------------------------------------
    def is_enter_candidate(self) -> bool:
        return self.final_status == FINAL_ENTER_CANDIDATE

    def is_block(self) -> bool:
        return self.final_status == FINAL_BLOCK

    def to_dict(self) -> Dict[str, Any]:
        """Lossy-but-readable snapshot for logs / dashboards."""
        def _bo(b: Optional[BrainOutput]) -> Optional[Dict[str, Any]]:
            if b is None:
                return None
            return {
                "brain_name": b.brain_name,
                "decision": b.decision,
                "grade": b.grade.value,
                "reason": b.reason,
                "data_quality": b.data_quality,
                "should_block": b.should_block,
                "risk_flags": list(b.risk_flags),
                "confidence": float(b.confidence),
            }

        gd = self.gate_decision
        gate_view: Optional[Dict[str, Any]] = None
        if gd is not None:
            gate_view = {
                "gate_decision": getattr(gd.gate_decision, "value",
                                         str(gd.gate_decision)),
                "direction": getattr(gd.direction, "value", str(gd.direction)),
                "audit_id": gd.audit_id,
                "blocking_reason": gd.blocking_reason,
                "approval_reason": gd.approval_reason,
                "session_status": gd.session_status,
            }
        return {
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "timestamp_ny": self.timestamp_ny.isoformat(),
            "session_status": self.session_status,
            "final_status": self.final_status,
            "final_reason": self.final_reason,
            "decision_cycle_record_id": self.decision_cycle_record_id,
            "gate_audit_record_id": self.gate_audit_record_id,
            "errors": list(self.errors),
            "timings_ms": dict(self.timings_ms),
            "news_output": _bo(self.news_output),
            "market_output": _bo(self.market_output),
            "chart_output": _bo(self.chart_output),
            "gate_decision": gate_view,
        }
