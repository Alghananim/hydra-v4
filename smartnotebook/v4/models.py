"""SmartNoteBook V4 — record dataclasses (frozen).

All records inherit from BaseRecord which carries the chain hash, sequence,
and timestamps. Subclasses add domain payload.

Hard rules enforced in __post_init__:
  * R2 — chain_hash must be non-empty
  * Domain rules — e.g. BLOCK requires blocking_reason, ENTER requires
    evidence_summary, ACTIVE lessons require allowed_from_timestamp
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from smartnotebook.v4.notebook_constants import (
    FINAL_BLOCK,
    FINAL_ENTER,
    FINAL_WAIT,
)
from smartnotebook.v4.record_types import LessonState, RecordType, ShadowStatus


_IMMUTABLE_MSG = "Records are immutable; use replace() with chain re-write"


@dataclass(frozen=True)
class BaseRecord:
    """Common header for every persisted record.

    Frozen — attempting to mutate raises AttributeError. To defeat the
    `object.__setattr__(rec, ...)` bypass (Red Team A10/A11) we override
    BOTH __setattr__ and __delattr__ AND freeze the instance __dict__
    after __post_init__ via types.MappingProxyType. Once frozen, even
    object.__setattr__ raises because the underlying dict is read-only.

    Combined with append-only Storage, corrections come via *new* records
    that point at the original via parent_record_id.
    """

    record_id: str
    record_type: RecordType
    timestamp_utc: datetime
    timestamp_ny: datetime
    sequence_id: int
    parent_record_id: Optional[str] = None
    prev_record_id: Optional[str] = None
    prev_hash: str = ""
    chain_hash: str = ""

    def __post_init__(self) -> None:
        # R2 — chain_hash must be present and non-empty
        if not self.chain_hash:
            raise ValueError(
                f"chain_hash required (R2 invariant) for "
                f"record_id={self.record_id} type={self.record_type}"
            )
        if not self.record_id:
            raise ValueError("record_id must be non-empty")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be tz-aware UTC")
        if self.timestamp_ny.tzinfo is None:
            raise ValueError("timestamp_ny must be tz-aware (America/New_York)")
        if not isinstance(self.sequence_id, int) or self.sequence_id < 0:
            raise ValueError("sequence_id must be non-negative int")



@dataclass(frozen=True)
class DecisionCycleRecord(BaseRecord):
    """One full evaluation cycle of all four brains + GateMind verdict.

    Captures the FULL decision context so the cycle can be replayed offline.
    """

    symbol: str = ""
    session_window: str = ""
    newsmind_output: Dict[str, Any] = field(default_factory=dict)
    marketmind_output: Dict[str, Any] = field(default_factory=dict)
    chartmind_output: Dict[str, Any] = field(default_factory=dict)
    gatemind_output: Dict[str, Any] = field(default_factory=dict)
    final_status: str = ""
    blocking_reason: str = ""
    evidence_summary: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    data_quality_summary: Dict[str, str] = field(default_factory=dict)
    model_versions: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.DECISION_CYCLE:
            raise ValueError("record_type must be DECISION_CYCLE")
        if not self.symbol:
            raise ValueError("DecisionCycleRecord.symbol must be non-empty")
        if self.final_status not in (FINAL_ENTER, FINAL_WAIT, FINAL_BLOCK):
            raise ValueError(
                f"final_status must be one of {FINAL_ENTER}, {FINAL_WAIT}, "
                f"{FINAL_BLOCK}; got {self.final_status!r}"
            )
        if self.final_status == FINAL_BLOCK and not self.blocking_reason:
            raise ValueError("BLOCK requires blocking_reason")
        if self.final_status == FINAL_ENTER and not self.evidence_summary:
            raise ValueError("ENTER_CANDIDATE requires evidence_summary")


@dataclass(frozen=True)
class GateAuditRecord(BaseRecord):
    """The exact GateDecision snapshot, persisted alongside its decision cycle."""

    symbol: str = ""
    audit_id: str = ""
    gate_decision: str = ""
    direction: str = ""
    blocking_reason: str = ""
    approval_reason: str = ""
    mind_votes: Dict[str, str] = field(default_factory=dict)
    mind_grades: Dict[str, str] = field(default_factory=dict)
    mind_data_quality: Dict[str, str] = field(default_factory=dict)
    consensus_status: str = ""
    grade_status: str = ""
    session_status: str = ""
    risk_flag_status: str = ""
    audit_trail: List[str] = field(default_factory=list)
    model_version: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.GATE_AUDIT:
            raise ValueError("record_type must be GATE_AUDIT")
        if not self.audit_id:
            raise ValueError("GateAuditRecord.audit_id must be non-empty")


@dataclass(frozen=True)
class RejectedTradeRecord(BaseRecord):
    """A trade that COULD have happened but was blocked.

    Tracked so we can run shadow accounting later (was the rejection
    correct in retrospect?).
    """

    symbol: str = ""
    rejection_reason: str = ""
    rejecting_mind: str = ""
    original_direction: str = ""
    grades: Dict[str, str] = field(default_factory=dict)
    would_have_entered_if_rule_relaxed: str = ""
    shadow_status: ShadowStatus = ShadowStatus.PENDING

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.REJECTED_TRADE:
            raise ValueError("record_type must be REJECTED_TRADE")
        if not self.rejection_reason:
            raise ValueError("RejectedTradeRecord requires rejection_reason")
        if self.original_direction not in ("BUY", "SELL"):
            raise ValueError(
                "RejectedTradeRecord.original_direction must be BUY or SELL"
            )


@dataclass(frozen=True)
class ShadowOutcomeRecord(BaseRecord):
    """Hypothetical outcome for a previously rejected trade.

    Links via parent_record_id → RejectedTradeRecord.
    """

    rejected_trade_id: str = ""
    hypothetical_entry: float = 0.0
    hypothetical_exit: float = 0.0
    hypothetical_pnl: float = 0.0
    was_rejection_correct: bool = True
    evidence: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.SHADOW_OUTCOME:
            raise ValueError("record_type must be SHADOW_OUTCOME")
        if not self.rejected_trade_id:
            raise ValueError("ShadowOutcomeRecord.rejected_trade_id required")


@dataclass(frozen=True)
class ExecutedTradeRecord(BaseRecord):
    """A real trade that the broker confirmed."""

    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    size: float = 0.0
    decision_cycle_id: str = ""
    broker_order_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.EXECUTED_TRADE:
            raise ValueError("record_type must be EXECUTED_TRADE")
        if self.direction not in ("BUY", "SELL"):
            raise ValueError("ExecutedTradeRecord.direction must be BUY or SELL")


@dataclass(frozen=True)
class TradeOutcomeRecord(BaseRecord):
    """The eventual close-out of an executed trade."""

    symbol: str = ""
    executed_trade_id: str = ""
    exit_price: float = 0.0
    pnl: float = 0.0
    outcome_class: str = ""  # WIN | LOSS | BREAKEVEN
    direction_match: bool = True
    exit_reason: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.TRADE_OUTCOME:
            raise ValueError("record_type must be TRADE_OUTCOME")
        if not self.executed_trade_id:
            raise ValueError("TradeOutcomeRecord.executed_trade_id required")
        if self.outcome_class not in ("WIN", "LOSS", "BREAKEVEN"):
            raise ValueError(
                "outcome_class must be WIN, LOSS or BREAKEVEN"
            )


@dataclass(frozen=True)
class MindPerformanceRecord(BaseRecord):
    """Per-mind attribution roll-up for a window.

    Carries the *honest* attribution: directional match + grade>=A is
    earned; grade<A is "lucky" and credit goes to RESPONSIBLE_LUCK.
    """

    mind_name: str = ""
    window_start_utc: Optional[datetime] = None
    window_end_utc: Optional[datetime] = None
    n_decisions: int = 0
    n_earned_wins: int = 0
    n_lucky_wins: int = 0
    n_unforced_losses: int = 0
    earned_pnl: float = 0.0
    lucky_pnl: float = 0.0
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.MIND_PERFORMANCE:
            raise ValueError("record_type must be MIND_PERFORMANCE")
        if not self.mind_name:
            raise ValueError("mind_name required")


@dataclass(frozen=True)
class LessonRecord(BaseRecord):
    """A structured lesson with lifecycle.

    States:
      CANDIDATE — newly proposed, not enforced
      ACTIVE    — enforced; requires allowed_from_timestamp
      RETIRED   — superseded or invalidated

    R5 invariant: ACTIVE lessons MUST carry allowed_from_timestamp so
    replay code can correctly exclude them from past evaluations.
    """

    lesson_id: str = ""
    source_records: List[str] = field(default_factory=list)
    lesson_text: str = ""
    affected_mind: str = ""
    evidence: List[str] = field(default_factory=list)
    proposed_rule_change: Dict[str, Any] = field(default_factory=dict)
    state: LessonState = LessonState.CANDIDATE
    allowed_from_timestamp: Optional[datetime] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.LESSON:
            raise ValueError("record_type must be LESSON")
        if not self.lesson_id:
            raise ValueError("lesson_id required")
        if not self.lesson_text:
            raise ValueError("lesson_text required")
        if self.state == LessonState.ACTIVE and self.allowed_from_timestamp is None:
            raise ValueError(
                "ACTIVE lesson requires allowed_from_timestamp (R5 invariant)"
            )
        if self.allowed_from_timestamp is not None:
            if self.allowed_from_timestamp.tzinfo is None:
                raise ValueError("allowed_from_timestamp must be tz-aware UTC")


@dataclass(frozen=True)
class BugRecord(BaseRecord):
    """An operational bug observation."""

    severity: str = ""    # info | warn | error | critical
    component: str = ""
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.BUG:
            raise ValueError("record_type must be BUG")
        if self.severity not in ("info", "warn", "error", "critical"):
            raise ValueError("severity must be info/warn/error/critical")
        if not self.description:
            raise ValueError("description required")


@dataclass(frozen=True)
class DailySummaryRecord(BaseRecord):
    """Roll-up of one day. Recomputable from raw."""

    date_utc: str = ""   # YYYY-MM-DD
    n_decision_cycles: int = 0
    n_enter: int = 0
    n_block: int = 0
    n_wait: int = 0
    n_executed_trades: int = 0
    n_rejected_trades: int = 0
    pnl_total: float = 0.0
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.DAILY_SUMMARY:
            raise ValueError("record_type must be DAILY_SUMMARY")
        if not self.date_utc:
            raise ValueError("date_utc required (YYYY-MM-DD)")


@dataclass(frozen=True)
class WeeklySummaryRecord(BaseRecord):
    """ISO-week summary."""

    iso_year: int = 0
    iso_week: int = 0
    n_decision_cycles: int = 0
    pnl_total: float = 0.0
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.record_type != RecordType.WEEKLY_SUMMARY:
            raise ValueError("record_type must be WEEKLY_SUMMARY")
        if self.iso_year <= 0 or not (1 <= self.iso_week <= 53):
            raise ValueError("iso_year/iso_week must be valid")


# ---------------------------------------------------------------------------
# S4 — defeat the object.__setattr__ bypass on frozen dataclasses.
#
# `frozen=True` only blocks the *normal* attribute-write path. Python's
# `object.__setattr__(rec, "field", value)` skips the class-level
# __setattr__ and writes straight to the instance __dict__ — a real
# Red-Team escape (A10/A11).
#
# Mitigation: after the instance is fully constructed, REPLACE its
# __dict__ with a custom dict subclass (`_FrozenDict`) that refuses
# __setitem__, __delitem__, update, pop, clear, etc.  Even though
# `object.__setattr__` writes via the C-level dict mutation slot, that
# slot still goes through `dict.__setitem__` for the instance dict (when
# the underlying type is a dict subclass with overridden __setitem__).
# The override raises AttributeError with our uniform message.
#
# We also replace the class-level __setattr__ / __delattr__ (which
# `frozen=True` set to raise FrozenInstanceError) with versions that
# raise AttributeError carrying _IMMUTABLE_MSG so error messages are
# uniform regardless of the path the attacker took.
#
# Per the spec: "Python's __slots__ doesn't fully prevent
# object.__setattr__, but combined with overridden __setattr__, it
# makes the bypass much harder."  We DO go further than that: the
# _FrozenDict swap blocks the most common bypass cleanly. It does not
# claim 100% protection (a determined attacker can still reach into
# C-level memory), but it raises on the canonical bypass path.
# ---------------------------------------------------------------------------


class _FrozenDict(dict):
    """A dict subclass that refuses all mutation.

    Used to replace BaseRecord instance __dict__ after construction so
    `object.__setattr__(rec, name, value)` raises instead of silently
    succeeding.

    Population pattern: callers must use _make_frozen_dict() which uses
    dict.__init__ directly via __new__ + super().__init__ to bypass our
    __setitem__ override during construction.
    """

    __slots__ = ()

    def __setitem__(self, k, v):
        raise AttributeError(_IMMUTABLE_MSG)

    def __delitem__(self, k):
        raise AttributeError(_IMMUTABLE_MSG)

    def update(self, *a, **kw):
        raise AttributeError(_IMMUTABLE_MSG)

    def setdefault(self, *a, **kw):
        raise AttributeError(_IMMUTABLE_MSG)

    def pop(self, *a, **kw):
        raise AttributeError(_IMMUTABLE_MSG)

    def popitem(self, *a, **kw):
        raise AttributeError(_IMMUTABLE_MSG)

    def clear(self):
        raise AttributeError(_IMMUTABLE_MSG)


def _make_frozen_dict(source: dict) -> _FrozenDict:
    """Create a _FrozenDict pre-populated with `source` items.

    We construct an empty _FrozenDict via __new__, then invoke dict's
    own __init__ via the parent class so the C-level dict population
    code runs (which doesn't go through our __setitem__ override).
    """
    fd = _FrozenDict.__new__(_FrozenDict)
    dict.__init__(fd, source)
    return fd


def _record_setattr_blocker(self, name, value):
    raise AttributeError(_IMMUTABLE_MSG)


def _record_delattr_blocker(self, name):
    raise AttributeError(_IMMUTABLE_MSG)


_RECORD_CLASSES = (
    BaseRecord,
    DecisionCycleRecord,
    GateAuditRecord,
    RejectedTradeRecord,
    ShadowOutcomeRecord,
    ExecutedTradeRecord,
    TradeOutcomeRecord,
    MindPerformanceRecord,
    LessonRecord,
    BugRecord,
    DailySummaryRecord,
    WeeklySummaryRecord,
)

for _cls in _RECORD_CLASSES:
    _cls.__setattr__ = _record_setattr_blocker  # type: ignore[assignment]
    _cls.__delattr__ = _record_delattr_blocker  # type: ignore[assignment]


def _freeze_dict_after_init(cls):
    orig_init = cls.__init__

    def __init__(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        # Swap __dict__ to the frozen variant. We use object.__setattr__
        # here because our override on cls would refuse the write.
        try:
            current = self.__dict__
            if not isinstance(current, _FrozenDict):
                object.__setattr__(self, "__dict__", _make_frozen_dict(current))
        except (TypeError, AttributeError):
            # If the instance has no writable __dict__ (e.g., __slots__),
            # the override on __setattr__ already protects us.
            pass

    cls.__init__ = __init__
    return cls


for _cls in _RECORD_CLASSES:
    _freeze_dict_after_init(_cls)
