"""Declarative permission engine — single state -> grade table.

Phase 1 audit verdict: V3's 5-layer engine is REJECTED. V4 has ONE
function that consumes the named states and returns (grade, decision,
should_block, reason, hard_block_label).

GRADE_RULE (from audit):
  A+ requires:
    trend in {strong_up, strong_down}
    AND momentum == accelerating
    AND volatility == normal
    AND liquidity in {good, fair}
    AND correlation == normal
    AND news in {aligned, no_news}
    AND no contradiction high/critical
    AND data_quality == "good"

  Any failure of an A+ condition drops one tier.
  Any HARD_BLOCK forces BLOCK regardless.

HARD_BLOCKs:
  - data_quality in {"missing", "broken"}
  - liquidity == "off-session"          (treat NY-off as BLOCK for FX majors)
  - volatility == "dangerous"
  - news_state == "block"               (NewsMind already said BLOCK)
  - contradiction critical (not currently produced; reserved)

The decision mapping:
  grade == BLOCK     -> "BLOCK"
  trend strong_up    -> "BUY"  (with grade A or better, else "WAIT")
  trend strong_down  -> "SELL" (with grade A or better, else "WAIT")
  otherwise          -> "WAIT"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from contracts.brain_output import BrainGrade


_GRADE_ORDER = [BrainGrade.BLOCK, BrainGrade.C, BrainGrade.B, BrainGrade.A, BrainGrade.A_PLUS]


def _step_down(g: BrainGrade) -> BrainGrade:
    """Drop one tier (A+ -> A -> B -> C -> BLOCK never happens here)."""
    idx = _GRADE_ORDER.index(g)
    if idx <= 1:  # already C; drop to C, never to BLOCK from a single 'failure'
        return BrainGrade.C
    return _GRADE_ORDER[idx - 1]


def _cap(grade: BrainGrade, cap: BrainGrade) -> BrainGrade:
    """Return min(grade, cap) by tier."""
    return grade if _GRADE_ORDER.index(grade) <= _GRADE_ORDER.index(cap) else cap


@dataclass
class PermissionInputs:
    trend_state: str
    momentum_state: str
    volatility_state: str
    liquidity_state: str
    correlation_status: str             # "normal" | "broken" | "unavailable"
    news_state: str                     # "aligned" | "no_news" | "warning" | "block"
    contradiction_severity: Optional[str]  # None | "medium" | "high" | "critical"
    data_quality: str                   # "good" | "stale" | "missing" | "broken"


@dataclass
class PermissionResult:
    grade: BrainGrade
    decision: str
    should_block: bool
    reason: str
    hard_block_label: Optional[str]
    failures: List[str]


def decide(inp: PermissionInputs, news_grade_cap: Optional[BrainGrade] = None) -> PermissionResult:
    failures: List[str] = []
    hard: Optional[str] = None

    # ---- HARD BLOCKs --------------------------------------------------
    if inp.data_quality in ("missing", "broken"):
        hard = f"data_quality={inp.data_quality}"
    elif inp.liquidity_state == "off-session":
        hard = "liquidity=off-session"
    elif inp.volatility_state == "dangerous":
        hard = "volatility=dangerous"
    elif inp.news_state == "block":
        hard = "news=block"
    elif inp.contradiction_severity == "critical":
        hard = "contradiction=critical"

    if hard:
        return PermissionResult(
            grade=BrainGrade.BLOCK,
            decision="BLOCK",
            should_block=True,
            reason=f"HARD_BLOCK: {hard}",
            hard_block_label=hard,
            failures=[hard],
        )

    # ---- A+ requirements ---------------------------------------------
    grade = BrainGrade.A_PLUS
    if inp.trend_state not in ("strong_up", "strong_down"):
        failures.append(f"trend={inp.trend_state}")
        grade = _step_down(grade)
    if inp.momentum_state != "accelerating":
        failures.append(f"momentum={inp.momentum_state}")
        grade = _step_down(grade)
    if inp.volatility_state != "normal":
        failures.append(f"volatility={inp.volatility_state}")
        grade = _step_down(grade)
    if inp.liquidity_state not in ("good", "fair"):
        failures.append(f"liquidity={inp.liquidity_state}")
        grade = _step_down(grade)
    if inp.correlation_status not in ("normal", "unavailable"):
        # broken correlation = real failure; unavailable is informational
        failures.append(f"correlation={inp.correlation_status}")
        grade = _step_down(grade)
    if inp.news_state not in ("aligned", "no_news"):
        failures.append(f"news={inp.news_state}")
        grade = _step_down(grade)
    if inp.contradiction_severity == "high":
        # High contradiction caps at C — the docstring in contradictions.py
        # says "high -> cap at C" and the strict reading is the safer one.
        # A single _step_down from A+ only reaches A, which would still
        # permit a BUY/SELL — that contradicts the spec.
        failures.append("contradiction=high")
        grade = _cap(grade, BrainGrade.C)
    elif inp.contradiction_severity == "medium":
        # medium = cap at B, not a full step down from where we are
        failures.append("contradiction=medium")
        grade = _cap(grade, BrainGrade.B)
    if inp.data_quality != "good":
        # stale data alone caps at B
        failures.append(f"data_quality={inp.data_quality}")
        grade = _cap(grade, BrainGrade.B)

    # ---- NewsMind cap ------------------------------------------------
    if news_grade_cap is not None:
        before = grade
        grade = _cap(grade, news_grade_cap)
        if grade != before:
            failures.append(f"news_cap={news_grade_cap.value}")

    # ---- Decision ----------------------------------------------------
    if grade == BrainGrade.BLOCK:
        decision = "BLOCK"
        should_block = True
    elif inp.trend_state == "strong_up" and grade in (BrainGrade.A_PLUS, BrainGrade.A):
        decision = "BUY"
        should_block = False
    elif inp.trend_state == "strong_down" and grade in (BrainGrade.A_PLUS, BrainGrade.A):
        decision = "SELL"
        should_block = False
    else:
        decision = "WAIT"
        should_block = False

    reason = (
        f"grade={grade.value} via permission_table; "
        f"failures={failures or 'none'}"
    )
    return PermissionResult(
        grade=grade,
        decision=decision,
        should_block=should_block,
        reason=reason,
        hard_block_label=None,
        failures=failures,
    )
