"""GateMind V4 — Claude/LLM safety wrapper (downgrade-only).

DESIGN INVARIANT (locked):
    An LLM may DOWNGRADE a deterministic decision but may NEVER UPGRADE one.

Allowed downgrades:
  ENTER_CANDIDATE → WAIT
  ENTER_CANDIDATE → BLOCK
  WAIT            → BLOCK

Forbidden upgrades:
  WAIT            → ENTER_CANDIDATE
  BLOCK           → WAIT
  BLOCK           → ENTER_CANDIDATE

The wrapper is *not* called inside the deterministic ladder. It is provided
as an optional post-processor for layered review (e.g. a future Phase that
wants Claude as a sanity overseer). When called with no override it is a
no-op. Either way: the `final.gate_decision` after this wrapper can never
be more permissive than the input — that property is ENFORCED here.
"""

from __future__ import annotations

from dataclasses import replace
from enum import Enum
from typing import Optional

from gatemind.v4.models import GateDecision, GateOutcome, TradeDirection


class LLMOverride(Enum):
    """The only override values an LLM is allowed to emit.

    Naming note: the Phase 1 spec used the verbs {agree, downgrade, block}.
    The enum members use {NO_CHANGE, DOWNGRADE_TO_WAIT, DOWNGRADE_TO_BLOCK}
    for explicitness — same semantics, more self-documenting at the call
    site. See `AGREE`/`DOWNGRADE`/`BLOCK` aliases below for spec alignment.
    """
    NO_CHANGE = "NO_CHANGE"
    DOWNGRADE_TO_WAIT = "DOWNGRADE_TO_WAIT"
    DOWNGRADE_TO_BLOCK = "DOWNGRADE_TO_BLOCK"


# Phase 1 spec aliases (cosmetic — the spec said {agree, downgrade, block}
# while we ship {NO_CHANGE, DOWNGRADE_TO_WAIT, DOWNGRADE_TO_BLOCK}). Python
# stdlib Enum forbids reassigning members directly, so we expose a parallel
# constants table that maps the spec verbs to canonical enum members.
LLM_OVERRIDE_SPEC_ALIASES = {
    "agree": LLMOverride.NO_CHANGE,
    "downgrade": LLMOverride.DOWNGRADE_TO_WAIT,
    "block": LLMOverride.DOWNGRADE_TO_BLOCK,
}


_PERMISSIVENESS = {
    GateOutcome.BLOCK: 0,
    GateOutcome.WAIT: 1,
    GateOutcome.ENTER_CANDIDATE: 2,
}


def _is_downgrade(before: GateOutcome, after: GateOutcome) -> bool:
    return _PERMISSIVENESS[after] < _PERMISSIVENESS[before]


def _is_no_change(before: GateOutcome, after: GateOutcome) -> bool:
    return after == before


def apply_llm_review(
    decision: GateDecision,
    override: LLMOverride = LLMOverride.NO_CHANGE,
    rationale: str = "",
) -> GateDecision:
    """Apply a downgrade-only LLM override.

    Returns a *new* GateDecision (since GateDecision is frozen). Raises
    PermissionError on any attempted upgrade — explicit failure rather than
    silent suppression so the engineer notices immediately.
    """
    if override == LLMOverride.NO_CHANGE:
        return decision

    if override == LLMOverride.DOWNGRADE_TO_WAIT:
        target = GateOutcome.WAIT
    elif override == LLMOverride.DOWNGRADE_TO_BLOCK:
        target = GateOutcome.BLOCK
    else:  # pragma: no cover — enum exhaustion
        raise PermissionError(f"unknown_llm_override:{override}")

    if not _is_downgrade(decision.gate_decision, target):
        # Includes attempted upgrade AND attempted "downgrade" to the same level.
        raise PermissionError(
            f"llm_cannot_change_{decision.gate_decision.value}_to_{target.value}"
        )

    # Build the downgraded decision: clear trade_candidate, set direction NONE,
    # append rationale to audit trail.
    new_audit = list(decision.audit_trail) + [
        f"LLM_override:{override.value}:rationale={rationale or 'unspecified'}"
    ]

    if target == GateOutcome.WAIT:
        return replace(
            decision,
            gate_decision=GateOutcome.WAIT,
            direction=TradeDirection.NONE,
            blocking_reason="",
            approval_reason="",
            trade_candidate=None,
            audit_trail=new_audit,
        )
    # BLOCK
    return replace(
        decision,
        gate_decision=GateOutcome.BLOCK,
        direction=TradeDirection.NONE,
        blocking_reason=f"llm_downgraded_block:{rationale or 'unspecified'}",
        approval_reason="",
        trade_candidate=None,
        audit_trail=new_audit,
    )
