"""GateMind V4 — local data contracts.

Imports the shared `BrainOutput` from contracts/. Defines:
  - GateOutcome enum
  - TradeDirection enum
  - TradeCandidate (frozen, populated only on ENTER_CANDIDATE)
  - GateDecision (frozen, every gate evaluation returns one)

Invariants enforced in __post_init__:
  * trade_candidate populated IFF gate_decision == ENTER_CANDIDATE
  * ENTER_CANDIDATE requires direction in {BUY, SELL}
  * BLOCK / WAIT must have direction == NONE-or-not-required and trade_candidate is None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

# Re-export BrainOutput contract for convenience
from contracts.brain_output import BrainGrade, BrainOutput  # noqa: F401

from gatemind.v4.gatemind_constants import GATE_NAME, MODEL_VERSION


class GateOutcome(Enum):
    ENTER_CANDIDATE = "ENTER_CANDIDATE"
    WAIT = "WAIT"
    BLOCK = "BLOCK"


class TradeDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NONE = "NONE"


@dataclass(frozen=True)
class TradeCandidate:
    """Constructed IFF GateMind says ENTER_CANDIDATE.

    GateMind does NOT compute SL/TP/size — that is downstream. This object is
    purely the *fact* that three brains agreed, with grades and supporting
    evidence preserved for audit.
    """
    symbol: str
    direction: TradeDirection
    approved_by: List[str]
    approval_grades: Dict[str, str]
    evidence_summary: List[str]
    risk_flags: List[str]
    timestamp_utc: datetime
    timestamp_ny: datetime

    def __post_init__(self) -> None:
        if self.direction not in (TradeDirection.BUY, TradeDirection.SELL):
            raise ValueError(
                f"TradeCandidate.direction must be BUY or SELL, got {self.direction}"
            )
        if not self.symbol or not self.symbol.strip():
            raise ValueError("TradeCandidate.symbol must be non-empty")
        if not self.approved_by:
            raise ValueError("TradeCandidate.approved_by must list at least one brain")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("TradeCandidate.timestamp_utc must be tz-aware")


@dataclass(frozen=True)
class GateDecision:
    """The single return type of GateMindV4.evaluate().

    Reproducibility: an audit_id keyed snapshot is sufficient to replay this
    decision in the audit_log module.
    """
    gate_name: str = GATE_NAME
    audit_id: str = ""
    timestamp_utc: Optional[datetime] = None
    timestamp_ny: Optional[datetime] = None
    symbol: str = ""

    gate_decision: GateOutcome = GateOutcome.BLOCK
    direction: TradeDirection = TradeDirection.NONE
    blocking_reason: str = ""
    approval_reason: str = ""

    mind_votes: Dict[str, str] = field(default_factory=dict)
    mind_grades: Dict[str, str] = field(default_factory=dict)
    mind_data_quality: Dict[str, str] = field(default_factory=dict)

    consensus_status: str = ""
    grade_status: str = ""
    session_status: str = ""
    risk_flag_status: str = ""

    trade_candidate: Optional[TradeCandidate] = None
    audit_trail: List[str] = field(default_factory=list)
    model_version: str = MODEL_VERSION

    def __post_init__(self) -> None:
        # Invariant: candidate populated IFF ENTER_CANDIDATE
        if self.gate_decision == GateOutcome.ENTER_CANDIDATE:
            if self.trade_candidate is None:
                raise ValueError("ENTER_CANDIDATE requires trade_candidate")
            if self.direction == TradeDirection.NONE:
                raise ValueError(
                    "ENTER_CANDIDATE requires direction BUY or SELL"
                )
        else:
            if self.trade_candidate is not None:
                raise ValueError(
                    "Non-ENTER outcomes must have trade_candidate=None"
                )

        # BLOCK must carry a blocking_reason
        if self.gate_decision == GateOutcome.BLOCK and not self.blocking_reason:
            raise ValueError("BLOCK gate_decision requires non-empty blocking_reason")

        # Audit trail must contain at least one rule entry once populated
        # (constructed by orchestrator — left flexible for unit tests)

    def is_enter(self) -> bool:
        return self.gate_decision == GateOutcome.ENTER_CANDIDATE

    def is_block(self) -> bool:
        return self.gate_decision == GateOutcome.BLOCK

    def is_wait(self) -> bool:
        return self.gate_decision == GateOutcome.WAIT


def utc_now() -> datetime:
    """Helper — tz-aware UTC now."""
    return datetime.now(timezone.utc)
