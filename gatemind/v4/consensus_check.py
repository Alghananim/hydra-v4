"""GateMind V4 — 3/3 consensus checks (V4.7 architectural fix)."""

from __future__ import annotations

from typing import Dict, Tuple

from contracts.brain_output import BrainGrade, BrainOutput

from gatemind.v4.gatemind_constants import (
    ALLOWED_GRADES,
    BLOCK_DECISION,
    DIRECTIONAL_DECISIONS,
    WAIT_DECISION,
)


def collect_decisions(news, market, chart) -> Dict[str, str]:
    return {
        "NewsMind": news.decision,
        "MarketMind": market.decision,
        "ChartMind": chart.decision,
    }


def collect_grades(news, market, chart) -> Dict[str, str]:
    return {
        "NewsMind": news.grade.value,
        "MarketMind": market.grade.value,
        "ChartMind": chart.grade.value,
    }


def collect_data_quality(news, market, chart) -> Dict[str, str]:
    return {
        "NewsMind": news.data_quality,
        "MarketMind": market.data_quality,
        "ChartMind": chart.data_quality,
    }


def all_grades_pass(news, market, chart) -> Tuple[bool, str]:
    """V12-F2: split chart vs vetoer thresholds.

    Old behaviour: every brain had to be A or A+; B at any brain blocked.
    Audit showed 19,323 of 19,392 in-window cycles (99.64%) died here —
    almost always because NewsMind or MarketMind landed on B while
    ChartMind was correctly A. Throwing away a tradeable chart signal
    because the vetoer's confidence ladder was at B (not actively
    blocking, just less certain) is the V5 bottleneck.

    V12 rule:
      - ChartMind grade MUST be A or A+ (it's the directional voice).
      - NewsMind / MarketMind grade may be B (vetoer mode); only their
        BLOCK decision (caught upstream) actually kills the cycle.
      - C / BLOCK at any brain still fails.
    """
    chart_g = chart.grade.value
    if chart_g not in ALLOWED_GRADES:
        return False, "below_threshold"  # canonical reason — preserved
    vetoer_grades = (news.grade.value, market.grade.value)
    for g in vetoer_grades:
        if g not in ("A", "A+", "B"):
            return False, "below_threshold"
    if chart.grade == BrainGrade.A_PLUS and all(
        g.value == "A+" for g in (news.grade, market.grade)
    ):
        return True, "all_a_plus"
    return True, "chart_a_vetoers_b_or_better"


def consensus_status(news, market, chart) -> Tuple[str, str | None]:
    """V4.7: ChartMind is directional voice; News/Market vetoers."""
    decisions = [news.decision, market.decision, chart.decision]

    if any(d == BLOCK_DECISION for d in decisions):
        return "any_block", None

    if all(d == WAIT_DECISION for d in decisions):
        return "unanimous_wait", None

    chart_d = chart.decision
    if chart_d in ("BUY", "SELL"):
        opposing = "SELL" if chart_d == "BUY" else "BUY"
        if news.decision == opposing or market.decision == opposing:
            return "directional_conflict", None
        if chart_d == "BUY":
            return "unanimous_buy", "BUY"
        return "unanimous_sell", "SELL"

    return "incomplete_agreement", None
