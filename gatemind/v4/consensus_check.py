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
    grades = [news.grade, market.grade, chart.grade]
    for g in grades:
        if g.value not in ALLOWED_GRADES:
            return False, "below_threshold"
    if all(g == BrainGrade.A_PLUS for g in grades):
        return True, "all_a_plus"
    return True, "all_a_or_better"


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
