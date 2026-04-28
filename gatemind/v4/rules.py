"""GateMind V4 — 8 rules, ordered, short-circuit ladder.

Each rule is a pure predicate function with the signature:

    rule(ctx: RuleContext) -> RuleResult

A RuleResult declares one of three outcomes:
    PASS   → keep walking the ladder
    BLOCK  → return GateOutcome.BLOCK with reason
    WAIT   → return GateOutcome.WAIT with reason
    ENTER  → return GateOutcome.ENTER_CANDIDATE (only R8 can do this)

Rule order is locked — DO NOT reorder without re-auditing. The ladder is
walked in `evaluate_rules()` which is the deterministic decision oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple

from gatemind.v4 import consensus_check
from gatemind.v4 import risk_flag_classifier
from gatemind.v4 import schema_validator
from gatemind.v4 import session_check
from gatemind.v4.gatemind_constants import (
    REASON_BRAIN_BLOCK,
    REASON_DIRECTIONAL_CONFLICT,
    REASON_GRADE_BELOW,
    REASON_INCOMPLETE_AGREEMENT,
    REASON_KILL_FLAG,
    REASON_OUTSIDE_NY,
    REASON_PARTIAL_DEFAULT,
    REASON_SCHEMA_INVALID,
    REASON_UNANIMOUS_WAIT,
    REASON_APPROVED,
)
from gatemind.v4.models import GateOutcome, TradeDirection


class _Verdict(Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    WAIT = "WAIT"
    ENTER = "ENTER"


@dataclass
class RuleContext:
    """Shared context passed down the ladder. Mutable: rules append to audit_trail
    but never replace it. Final decision fields are read by the orchestrator."""
    news: Any
    market: Any
    chart: Any
    now_utc: datetime
    symbol: str

    # Computed during the walk and reused by later rules
    session_label: str = ""
    grade_status: str = ""
    consensus_label: str = ""
    consensus_direction: Optional[str] = None
    risk_status: str = ""
    kill_offenders: Tuple[str, ...] = ()
    warning_flags: Tuple[str, ...] = ()
    audit_trail: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.audit_trail is None:
            self.audit_trail = []


@dataclass
class RuleResult:
    verdict: _Verdict
    reason: str = ""
    direction: TradeDirection = TradeDirection.NONE
    detail: str = ""


# ---------------------------------------------------------------------------
# R1 — Schema validation
# ---------------------------------------------------------------------------
def r1_schema(ctx: RuleContext) -> RuleResult:
    ok, brain, reason = schema_validator.validate_all(ctx.news, ctx.market, ctx.chart)
    ctx.audit_trail.append(f"R1_schema:{'PASS' if ok else f'FAIL:{brain}:{reason}'}")
    if not ok:
        return RuleResult(_Verdict.BLOCK, REASON_SCHEMA_INVALID, detail=f"{brain}:{reason}")
    return RuleResult(_Verdict.PASS)


# ---------------------------------------------------------------------------
# R2 — New York session window
# ---------------------------------------------------------------------------
def r2_session(ctx: RuleContext) -> RuleResult:
    in_window, label = session_check.is_in_ny_window(ctx.now_utc)
    ctx.session_label = label
    ctx.audit_trail.append(f"R2_session:{label}")
    if not in_window:
        return RuleResult(_Verdict.BLOCK, REASON_OUTSIDE_NY, detail=label)
    return RuleResult(_Verdict.PASS)


# ---------------------------------------------------------------------------
# R3 — Grade threshold (A or A+ only)
# ---------------------------------------------------------------------------
def r3_grade(ctx: RuleContext) -> RuleResult:
    ok, status = consensus_check.all_grades_pass(ctx.news, ctx.market, ctx.chart)
    ctx.grade_status = status
    ctx.audit_trail.append(f"R3_grade:{status}")
    if not ok:
        return RuleResult(_Verdict.BLOCK, REASON_GRADE_BELOW, detail=status)
    return RuleResult(_Verdict.PASS)


# ---------------------------------------------------------------------------
# R4 — Any brain says should_block
# ---------------------------------------------------------------------------
def r4_brain_block(ctx: RuleContext) -> RuleResult:
    offenders = []
    for label, brain in (("NewsMind", ctx.news), ("MarketMind", ctx.market), ("ChartMind", ctx.chart)):
        if brain.should_block:
            offenders.append(label)
    ctx.audit_trail.append(
        f"R4_brain_block:{'PASS' if not offenders else 'FAIL:' + ','.join(offenders)}"
    )
    if offenders:
        return RuleResult(_Verdict.BLOCK, REASON_BRAIN_BLOCK, detail=",".join(offenders))
    return RuleResult(_Verdict.PASS)


# ---------------------------------------------------------------------------
# R5 — Kill-class risk flags
# ---------------------------------------------------------------------------
def r5_kill_flag(ctx: RuleContext) -> RuleResult:
    kill, warn, unknown = risk_flag_classifier.aggregate_flags(ctx.news, ctx.market, ctx.chart)
    ctx.warning_flags = tuple(warn)
    offenders = list(kill) + list(unknown)
    ctx.kill_offenders = tuple(offenders)
    ctx.risk_status = risk_flag_classifier.risk_flag_status(kill, warn, unknown)
    ctx.audit_trail.append(
        f"R5_kill_flag:{ctx.risk_status}"
        + (f":{','.join(offenders)}" if offenders else "")
    )
    if offenders:
        return RuleResult(_Verdict.BLOCK, REASON_KILL_FLAG, detail=",".join(offenders))
    return RuleResult(_Verdict.PASS)


# ---------------------------------------------------------------------------
# R6 — Directional conflict (BUY vs SELL within the trio)
# ---------------------------------------------------------------------------
def r6_direction(ctx: RuleContext) -> RuleResult:
    label, common = consensus_check.consensus_status(ctx.news, ctx.market, ctx.chart)
    ctx.consensus_label = label
    ctx.consensus_direction = common
    ctx.audit_trail.append(f"R6_direction:{label}")
    if label == "directional_conflict":
        return RuleResult(_Verdict.BLOCK, REASON_DIRECTIONAL_CONFLICT, detail=label)
    if label == "incomplete_agreement":
        return RuleResult(_Verdict.BLOCK, REASON_INCOMPLETE_AGREEMENT, detail=label)
    if label == "any_block":
        # R4 should have caught a should_block path, but a brain decision=="BLOCK"
        # without should_block is a contract violation we still treat as BLOCK.
        return RuleResult(_Verdict.BLOCK, REASON_BRAIN_BLOCK, detail=label)
    return RuleResult(_Verdict.PASS)


# ---------------------------------------------------------------------------
# R7 — Unanimous WAIT
# ---------------------------------------------------------------------------
def r7_unanimous_wait(ctx: RuleContext) -> RuleResult:
    if ctx.consensus_label == "unanimous_wait":
        ctx.audit_trail.append("R7_unanimous_wait:WAIT")
        return RuleResult(_Verdict.WAIT, REASON_UNANIMOUS_WAIT)
    ctx.audit_trail.append("R7_unanimous_wait:PASS")
    return RuleResult(_Verdict.PASS)


# ---------------------------------------------------------------------------
# R8 — ENTER_CANDIDATE iff unanimous BUY or SELL
# ---------------------------------------------------------------------------
def r8_enter(ctx: RuleContext) -> RuleResult:
    if ctx.consensus_label == "unanimous_buy":
        ctx.audit_trail.append("R8_enter:ENTER:BUY")
        return RuleResult(_Verdict.ENTER, REASON_APPROVED, direction=TradeDirection.BUY)
    if ctx.consensus_label == "unanimous_sell":
        ctx.audit_trail.append("R8_enter:ENTER:SELL")
        return RuleResult(_Verdict.ENTER, REASON_APPROVED, direction=TradeDirection.SELL)
    # Defensive default — should be unreachable if R6/R7 worked
    ctx.audit_trail.append("R8_enter:WAIT:partial_state_default")
    return RuleResult(_Verdict.WAIT, REASON_PARTIAL_DEFAULT)


# ---------------------------------------------------------------------------
# Locked ladder
# ---------------------------------------------------------------------------
RULE_LADDER: Tuple[Callable[[RuleContext], RuleResult], ...] = (
    r1_schema,
    r2_session,
    r3_grade,
    r4_brain_block,
    r5_kill_flag,
    r6_direction,
    r7_unanimous_wait,
    r8_enter,
)


def evaluate_rules(ctx: RuleContext) -> RuleResult:
    """Walk the ladder; first non-PASS wins. Always returns a terminal result."""
    for rule in RULE_LADDER:
        result = rule(ctx)
        if result.verdict != _Verdict.PASS:
            return result
    # If every rule returned PASS we have a logic bug — fail-closed.
    ctx.audit_trail.append("ladder_fallthrough:fail_closed")
    return RuleResult(_Verdict.BLOCK, "ladder_fallthrough", detail="unreachable")
